// Private data stays in IndexedDB, never in the service worker's public cache.
const clone = (value) => structuredClone(value);
const reply = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
const empty = () => ({ ownerId: null, locked: false, cache: {}, queue: [], nextId: -1000000 });
const cacheable = (path) => /^\/api\/(me|pets|reminders)$/.test(path)
  || /^\/api\/pets\/\d+(?:\/(weights|observations|history|summary)(?:\?.*)?)?$/.test(path)
  || path.startsWith('/api/followups/due');
function operation(path, method) {
  if (path === '/api/reminders' && method === 'POST') return 'reminder';
  if (/^\/api\/reminders\/-?\d+$/.test(path) && method === 'DELETE') return 'disable';
  if (/^\/api\/pets\/\d+\/weights$/.test(path) && method === 'POST') return 'weight';
  if (/^\/api\/pets\/\d+\/observations$/.test(path) && method === 'POST') return 'observation';
  if (/^\/api\/pets\/\d+\/photo$/.test(path) && ['POST', 'DELETE'].includes(method)) return 'photo';
  return '';
}

export function indexedWorkspace() {
  const database = new Promise((resolve, reject) => {
    const request = indexedDB.open('temichevvet-private-workspace', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('workspace');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  async function transact(mode, value) {
    const db = await database;
    return new Promise((resolve, reject) => {
      const tx = db.transaction('workspace', mode);
      const store = tx.objectStore('workspace');
      const request = mode === 'readonly' ? store.get('current') : store.put(value, 'current');
      tx.oncomplete = () => resolve(request.result);
      tx.onerror = tx.onabort = () => reject(tx.error || new Error('offline_storage_unavailable'));
    });
  }
  return { load: () => transact('readonly'), save: (value) => transact('readwrite', value) };
}

export class OfflineClient {
  constructor({ transport, storage, changed = () => {}, online = () => navigator.onLine, uuid = () => crypto.randomUUID() }) {
    Object.assign(this, { transport, storage, changed, online, uuid });
    this.state = empty(); this.connected = true; this.writes = Promise.resolve(); this.syncing = null;
    this.ready = storage.load().then((value) => { if (value) this.state = value; }).catch(() => { this.storageFailed = true; });
  }
  status() {
    return { offline: !this.online() || !this.connected, pending: this.state.queue.length,
      failed: this.state.queue.filter((job) => job.error).length, updateRequired: Boolean(this.updateRequired), locked: this.state.locked && Boolean(this.state.ownerId) };
  }
  async persist() {
    const value = clone(this.state);
    this.writes = this.writes.catch(() => {}).then(() => this.storage.save(value));
    try { await this.writes; } catch { this.storageFailed = true; throw new Error('offline_storage_unavailable'); }
    this.changed(this.status());
  }
  async clear() { await this.ready; this.state = empty(); await this.persist(); }
  async lock() { this.state.locked = true; await this.persist(); }
  async remember(path, data) {
    if (path === '/api/me' && data.user?.id) {
      if (this.state.ownerId && Number(data.user.id) !== this.state.ownerId) this.state = empty();
      this.state.ownerId = Number(data.user.id); this.state.locked = false;
    }
    if (!this.state.ownerId || this.state.locked || !cacheable(path)) return;
    this.state.cache[path] = clone(data);
    const match = path.match(/^\/api\/pets\/(\d+)$/);
    if (match) {
      for (const key of ['weights', 'observations', 'history']) this.state.cache[`${path}/${key}`] ||= { items: clone(data[key] || []) };
      const list = this.state.cache['/api/pets'];
      if (list) list.items = list.items.map((pet) => pet.id === data.item.id ? clone(data.item) : pet);
    }
    await this.persist();
  }
  pet(id) { return this.state.cache['/api/pets']?.items?.find((pet) => Number(pet.id) === Number(id)); }
  async hydrate() {
    await this.ready;
    if (!this.online() || this.state.locked || !this.state.ownerId) return;
    const key = `${this.state.ownerId}:${(this.state.cache['/api/pets']?.items || []).map((pet) => pet.id).join(',')}`;
    if (this.hydrating || (this.hydratedKey === key && Date.now() - this.hydratedAt < 60000)) return;
    this.hydrating = true; this.hydratedKey = key; this.hydratedAt = Date.now();
    const owner = this.state.ownerId;
    try { for (const pet of this.state.cache['/api/pets']?.items || []) {
      const path = `/api/pets/${pet.id}`;
      try {
        const response = await this.transport(path, { credentials: 'same-origin' });
        if (this.state.ownerId !== owner || this.state.locked) return;
        if (response.ok) await this.remember(path, await response.json());
        else if ([401, 403].includes(response.status)) { await this.lock(); return; }
      } catch { return; }
    } } finally { this.hydrating = false; }
  }
  row(job) {
    const p = job.payload;
    if (job.kind === 'disable' || job.kind === 'photo') return null;
    const row = { ...p, id: job.localId, created_at: job.createdAt, updated_at: job.createdAt,
      user_id: this.state.ownerId, pet_id: job.petId, is_active: 1, offline_pending: true, sync_error: job.error || '' };
    if (job.kind === 'observation') row.payload = { text: p.text };
    if (job.kind === 'reminder') Object.assign(row, { pet_name: this.pet(job.petId)?.pet_name, pet_type: this.pet(job.petId)?.pet_type });
    return row;
  }
  project(path) {
    let data = clone(this.state.cache[path] || null);
    const petId = Number(path.match(/^\/api\/pets\/(\d+)/)?.[1] || 0);
    if (!data && petId && this.pet(petId)) {
      if (/\/(weights|observations|history)$/.test(path)) data = { items: [] };
      else if (path === `/api/pets/${petId}`) data = { item: clone(this.pet(petId)), reminders: [], weights: [], observations: [], history: [] };
    }
    if (!data && path === '/api/reminders' && this.state.ownerId) data = { items: [] };
    if (!data && path.startsWith('/api/followups/due') && this.state.ownerId) data = { items: [] };
    if (!data) return null;
    for (const job of this.state.queue) this.apply(data, path, job, this.row(job));
    return data;
  }
  apply(data, path, job, row) {
    const detail = path === `/api/pets/${job.petId}`;
    const put = (key, record) => {
      const items = data[key] || [];
      data[key] = [record, ...items.filter((item) => item.id !== job.localId && item.id !== record.id
        && !(record.client_request_id && item.client_request_id === record.client_request_id))];
    };
    if (job.kind === 'photo' || job.kind === 'weight') {
      const update = (pet) => {
        if (Number(pet.id) !== job.petId) return pet;
        return { ...pet, ...(job.kind === 'photo' ? { photo_data_url: job.method === 'DELETE' ? null : job.payload.data_url } : { weight_kg: job.payload.weight_kg }) };
      };
      if (path === '/api/pets') data.items = data.items.map(update);
      if (detail) data.item = update(data.item);
    }
    if (job.kind === 'disable') {
      if (path === '/api/reminders') data.items = data.items.filter((item) => item.id !== job.targetId);
      if (/^\/api\/pets\/\d+$/.test(path)) data.reminders = (data.reminders || []).filter((item) => item.id !== job.targetId);
      return;
    }
    const keys = { reminder: 'reminders', weight: 'weights', observation: 'observations' };
    const key = keys[job.kind];
    if (!key || !row) return;
    if (detail) put(key, row);
    if ((key === 'reminders' && path === '/api/reminders') || path === `/api/pets/${job.petId}/${key}`) put('items', row);
    if (detail || path === `/api/pets/${job.petId}/history`) {
      const event = { id: job.localId, created_at: row.created_at, event_type: job.kind,
        title: {reminder: 'Напоминание добавлено', weight: 'Вес обновлён', observation: 'Наблюдение добавлено'}[job.kind],
        details: job.payload.text || job.payload.title || `${job.payload.weight_kg} кг`, offline_pending: row.offline_pending };
      put(detail ? 'history' : 'items', event);
    }
  }
  validate(kind, payload, petId) {
    if (petId && !this.pet(petId)) throw new Error('pet_not_found');
    const length = (value, min, max) => typeof value === 'string' && value.trim().length >= min && value.length <= max;
    if (kind === 'weight' && (!Number.isFinite(payload.weight_kg) || payload.weight_kg < 0.05 || payload.weight_kg > 200 || (payload.note || '').length > 300)) throw new Error('validation_error');
    if (kind === 'observation' && (!length(payload.text, 2, 2000) || payload.triage_id)) throw new Error('validation_error');
    if (kind === 'reminder') {
      const date = payload.due_date;
      if (!length(payload.title, 2, 120) || !/^\d{4}-\d{2}-\d{2}$/.test(date || '')
        || Number.isNaN(Date.parse(`${date}T12:00:00Z`)) || new Date(`${date}T12:00:00Z`).toISOString().slice(0, 10) !== date
        || (payload.due_time && !/^([01]\d|2[0-3]):[0-5]\d$/.test(payload.due_time)) || !['once','daily','weekly','monthly','every_3_months','every_6_months','yearly'].includes(payload.periodicity || 'once') || (payload.notes || '').length > 500) throw new Error('validation_error');
    }
    if (kind === 'photo' && payload.data_url && (!/^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(payload.data_url) || payload.data_url.length > 2_800_000)) throw new Error('pet_photo_invalid');
  }
  async enqueue(path, options, kind) {
    if (!this.state.ownerId || this.state.locked) return reply({ detail: 'authorization_required' }, 401);
    if (this.storageFailed) throw new Error('offline_storage_unavailable');
    const payload = options.body ? JSON.parse(options.body) : {};
    const petId = kind === 'reminder' ? Number(payload.pet_id) || null : Number(path.match(/^\/api\/pets\/(\d+)/)?.[1]) || null;
    this.validate(kind, payload, petId);
    const targetId = kind === 'disable' ? Number(path.split('/').pop()) : null;
    const job = { path, method: options.method.toUpperCase(), kind, petId, targetId, payload,
      requestId: payload.client_request_id || this.uuid(), localId: this.state.nextId--, createdAt: new Date().toISOString() };
    if (['reminder', 'weight', 'observation'].includes(kind)) payload.client_request_id = job.requestId;
    // A local reminder can be disabled before upload: retain both jobs if its create may be in flight.
    this.state.queue.push(job);
    try { await this.persist(); } catch (error) { this.state.queue = this.state.queue.filter((item) => item !== job); throw error; }
    void this.sync().catch(() => {});
    return reply({ item: this.row(job) || { ...this.pet(petId), photo_data_url: payload.data_url || null }, ok: true, offline_pending: true });
  }
  async request(path, options = {}) {
    await this.ready;
    const method = (options.method || 'GET').toUpperCase();
    const kind = operation(path, method);
    if (kind === 'observation' && JSON.parse(options.body || '{}').triage_id != null) {
      if (!this.online()) throw new Error('offline_internet_required');
      return this.transport(path, options);
    }
    if (kind) return this.enqueue(path, { ...options, method }, kind);
    if (method === 'GET' && cacheable(path)) {
      try {
        if (!this.online() || (!this.connected && Date.now() - (this.lastFailedAt || 0) < 15000)) throw new Error('offline');
        const response = await this.transport(path, options);
        if ([401, 403].includes(response.status)) { await this.lock(); return response; }
        if (response.status >= 500) throw new Error('server_unavailable');
        this.connected = true;
        if (!response.ok) { delete this.state.cache[path]; await this.persist(); return response; }
        const data = await response.json();
        await this.remember(path, data);
        const projected = this.state.locked ? data : this.project(path) || data;
        this.changed(this.status());
        return reply(projected);
      } catch (error) {
        if (this.connected) this.lastFailedAt = Date.now();
        this.connected = false; this.changed(this.status());
        const cached = !this.state.locked && this.project(path);
        if (cached) return reply(cached);
        throw error;
      }
    }
    if (!this.online()) throw new Error('offline_internet_required');
    return this.transport(path, options);
  }
  async sync() {
    await this.ready;
    if (this.syncing) return this.syncing;
    this.syncing = this.flush().finally(() => { this.syncing = null; });
    return this.syncing;
  }
  async flush() {
    if (!this.online() || !this.state.queue.length || this.state.locked) return;
    const ownerId = this.state.ownerId;
    try {
      // Verify the actual cookie session before sending any private queued write.
      const me = await this.transport('/api/me', { credentials: 'same-origin' });
      if ([401, 403].includes(me.status)) { await this.lock(); return; }
      if (!me.ok) throw new Error('server_unavailable');
      const account = await me.json();
      if (Number(account.user?.id) !== ownerId) { await this.lock(); return; }
      // Older servers cannot deduplicate retried writes. Keep the local queue until their upgrade.
      this.updateRequired = account.mobile_features?.offline_sync !== 1;
      if (this.updateRequired) { this.changed(this.status()); return; }
      this.connected = true;
      while (this.state.ownerId === ownerId && this.state.queue.length && !this.state.locked) {
        const job = this.state.queue[0];
        if (job.error) break;
        const response = await this.transport(job.path, { method: job.method, credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' }, ...(job.method !== 'DELETE' ? { body: JSON.stringify(job.payload) } : {}) });
        if (this.state.ownerId !== ownerId || this.state.locked) return;
        if ([401, 403].includes(response.status)) { await this.lock(); return; }
        if (response.status >= 500) throw new Error('server_unavailable');
        const data = await response.json().catch(() => ({}));
        if (!response.ok && !(job.kind === 'disable' && response.status === 404)) {
          job.error = typeof data.detail === 'string' ? data.detail : 'validation_error';
          await this.persist(); break;
        }
        if (job.kind === 'photo' && data.item) job.payload.data_url = data.item.photo_data_url;
        for (const [path, cached] of Object.entries(this.state.cache)) this.apply(cached, path, job, data.item);
        if (job.kind === 'reminder' && data.item) {
          for (const queued of this.state.queue) if (queued.kind === 'disable' && queued.targetId === job.localId) {
            queued.targetId = data.item.id; queued.path = `/api/reminders/${data.item.id}`;
          }
        }
        this.state.queue = this.state.queue.filter((item) => item.requestId !== job.requestId);
        await this.persist();
      }
    } catch { this.lastFailedAt = Date.now(); this.connected = false; this.changed(this.status()); }
  }
  async retry() { for (const job of this.state.queue) delete job.error; await this.persist(); return this.sync(); }
  async discard(requestId) {
    // The server may have accepted a write before losing the reply; review warns about this.
    this.state.queue = this.state.queue.filter((job) => job.requestId !== requestId);
    await this.persist();
  }
}
