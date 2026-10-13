import assert from 'node:assert/strict';
import { test } from 'node:test';
import { OfflineClient } from '../web/offline-store.js';
import { petAvatar } from '../web/pet-avatar.js';

const response = (data, status = 200) => new Response(JSON.stringify(data), {status});
function fixture() {
  let saved, online = false, user = 1, serial = 0, loseReply = false, fail = 0, supported = true;
  const accepted = new Map(), calls = [];
  const storage = {load: async () => saved && structuredClone(saved), save: async (value) => { saved = structuredClone(value); }};
  const transport = async (path, options = {}) => {
    calls.push({path, options});
    if (!online) throw new Error('network');
    if (path === '/api/me') return response(user ? {user:{id:user},mobile_features:supported ? {offline_sync:1} : {}} : {detail:'authorization_required'}, user ? 200 : 401);
    if (options.method === 'DELETE') return response({ok:true});
    if (options.method === 'POST') {
      if (fail) return response({detail:'reminder_limit_reached'}, fail);
      const payload = JSON.parse(options.body);
      const key = payload.client_request_id;
      if (!accepted.has(key)) accepted.set(key, {...payload, id:100 + accepted.size, created_at:new Date().toISOString()});
      if (loseReply) { loseReply = false; throw new Error('lost_response'); }
      return response({item:accepted.get(key)});
    }
    if (path === '/api/pets') return response({items:[{id:10,pet_name:'Лео',pet_type:'кошка'}]});
    if (path === '/api/pets/10') return response({item:{id:10,pet_name:'Лео',pet_type:'кошка'},reminders:[],weights:[],observations:[],history:[]});
    return response({items:[]});
  };
  const create = () => new OfflineClient({storage, transport, online:()=>online, uuid:()=>`fixture-request-${++serial}`});
  const client = create();
  async function prime() { online=true; await client.request('/api/me'); await client.request('/api/pets'); await client.request('/api/pets/10'); online=false; }
  return {client,create,prime,calls,accepted,storage,online:(value)=>{online=value;},user:(value)=>{user=value;},lose:()=>{loseReply=true;},fail:(value)=>{fail=value;},supported:(value)=>{supported=value;}};
}
const add = (client,path,payload) => client.request(path,{method:'POST',body:JSON.stringify(payload)}).then((r)=>r.json());
const reminder = {pet_id:10,title:'Обработка',due_date:'2026-10-20',due_time:'12:30',periodicity:'once'};

test('offline records and portraits survive a cold restart and appear in existing cards', async () => {
  const f=fixture(); await f.prime();
  await add(f.client,'/api/reminders',reminder);
  await add(f.client,'/api/pets/10/weights',{weight_kg:4.7,note:'Офлайн'});
  await add(f.client,'/api/pets/10/observations',{text:'Аппетит хороший',obs_type:'note'});
  await add(f.client,'/api/pets/10/photo',{data_url:'data:image/jpeg;base64,YQ=='});
  const restarted=f.create();
  assert.equal((await (await restarted.request('/api/me')).json()).user.id,1);
  const card=await (await restarted.request('/api/pets/10')).json();
  assert.equal(card.item.weight_kg,4.7); assert.ok(card.item.photo_data_url);
  assert.equal(card.reminders[0].title,'Обработка'); assert.equal(card.observations[0].payload.text,'Аппетит хороший');
  assert.equal(card.weights[0].offline_pending,true); assert.equal(restarted.status().pending,4);
});

test('a lost server reply retries the same key and removes the queue only after acknowledgment', async () => {
  const f=fixture(); await f.prime(); await add(f.client,'/api/reminders',reminder);
  f.online(true); f.lose(); await f.client.sync();
  assert.equal(f.accepted.size,1); assert.equal(f.client.status().pending,1);
  const restarted=f.create(); await restarted.sync();
  assert.equal(f.accepted.size,1); assert.equal(restarted.status().pending,0);
  const writes=f.calls.filter((call)=>call.options.method==='POST');
  assert.equal(JSON.parse(writes[0].options.body).client_request_id,JSON.parse(writes[1].options.body).client_request_id);
});

test('disabling a local reminder maps the temporary id to its acknowledged server id', async () => {
  const f=fixture(); await f.prime(); const saved=await add(f.client,'/api/reminders',reminder);
  await f.client.request(`/api/reminders/${saved.item.id}`,{method:'DELETE'});
  assert.equal((await (await f.client.request('/api/reminders')).json()).items.length,0);
  f.online(true); await f.client.sync();
  assert.equal(f.calls.find((call)=>call.options.method==='DELETE').path,'/api/reminders/100');
  assert.equal(f.client.status().pending,0);
});

test('validation and plan failures remain visible and durable until reviewed', async () => {
  const f=fixture(); await f.prime(); await add(f.client,'/api/reminders',reminder);
  f.online(true); f.fail(409); await f.client.sync();
  assert.equal(f.client.status().failed,1); assert.equal(f.client.status().pending,1);
  const restarted=f.create(); await restarted.ready; assert.equal(restarted.status().failed,1);
  f.fail(0); await restarted.retry(); assert.equal(restarted.status().pending,0);
});

test('queued writes are never sent under a different cookie account', async () => {
  const f=fixture(); await f.prime(); await add(f.client,'/api/reminders',reminder);
  f.online(true); f.user(2); await f.client.sync();
  assert.equal(f.accepted.size,0); assert.equal(f.client.status().locked,true);
  await f.client.request('/api/me');
  assert.equal(f.client.state.ownerId,2); assert.equal(f.client.status().pending,0);
  f.online(false); await assert.rejects(f.client.request('/api/pets/10'));
});

test('an explicit 401 locks cached private data, including after relaunch', async () => {
  const f=fixture(); await f.prime(); f.online(true); f.user(null);
  assert.equal((await f.client.request('/api/me')).status,401);
  f.online(false); await assert.rejects(f.create().request('/api/me'));
});

test('logout clears local records; storage failures never report a saved mutation', async () => {
  const f=fixture(); await f.prime(); await add(f.client,'/api/reminders',reminder); await f.client.clear();
  const restarted=f.create(); await restarted.ready; assert.equal(restarted.state.ownerId,null); assert.equal(restarted.status().pending,0);
  const broken=fixture(); await broken.prime(); broken.storage.save=async()=>{throw new Error('disk full');};
  await assert.rejects(add(broken.client,'/api/reminders',reminder),/offline_storage_unavailable/);
  assert.equal(broken.client.status().pending,0);
});

test('invalid offline dates, weights, unknown pets and online-only triage fail before storing', async () => {
  const f=fixture(); await f.prime();
  await assert.rejects(add(f.client,'/api/reminders',{...reminder,due_date:'2026-02-31'}));
  await assert.rejects(add(f.client,'/api/pets/10/weights',{weight_kg:NaN}));
  await assert.rejects(add(f.client,'/api/pets/99/weights',{weight_kg:2}));
  await assert.rejects(add(f.client,'/api/triage',{}),/offline_internet_required/);
  assert.equal(f.client.status().pending,0);
});

test('cat and dog fallbacks differ and uploaded portraits escape user labels', () => {
  assert.match(petAvatar({pet_type:'кошка'}),/aria-label="Кошка"/);
  assert.match(petAvatar({pet_type:'собака'}),/aria-label="Собака"/);
  assert.match(petAvatar({photo_data_url:'data:image/jpeg;base64,YQ==',pet_name:'<script>'}),/&lt;script&gt;/);
  assert.doesNotMatch(petAvatar({photo_data_url:'javascript:alert(1)'}),/javascript:/);
});

 test('a pre-upgrade server cannot receive queued writes until it advertises deduplication', async () => {
  const f=fixture(); await f.prime(); await add(f.client,'/api/reminders',reminder);
  f.online(true); f.supported(false); await f.client.sync();
  assert.equal(f.accepted.size,0); assert.equal(f.client.status().pending,1); assert.equal(f.client.status().updateRequired,true);
  f.supported(true); await f.client.sync(); assert.equal(f.accepted.size,1); assert.equal(f.client.status().pending,0);
});
 test('observations linked to an online triage keep their original direct save flow', async () => {
  const f=fixture(); await f.prime(); f.online(true);
  await add(f.client,'/api/pets/10/observations',{text:'Ответ по разбору',triage_id:12});
  assert.equal(f.client.status().pending,0); assert.equal(f.calls.at(-1).options.method,'POST');
});
