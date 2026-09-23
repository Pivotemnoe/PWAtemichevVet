import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(new URL("../web/app.js", import.meta.url), "utf8");
function definition(name) {
  const marker = new RegExp(`(?:async )?function ${name}\\(`).exec(source);
  assert.ok(marker, name);
  const rest = source.slice(marker.index);
  const next = /\n(?:async )?function /.exec(rest);
  return next ? rest.slice(0, next.index) : rest;
}

{
  const pending = { text: "Тестовый случай", answer: "Тестовый ответ", client_request_id: "stable-case", created_at: "2026-09-10T10:00:00Z", landing_slug: "cat-not-eating", pet_type: "cat", urgency: "green" };
  const node = { innerHTML: "", textContent: "", querySelector() { return {}; } };
  const events = [];
  let stores = 0;
  const ctx = {
    pendingPublicCheckSave: () => pending,
    CHECK_LANDING_VARIANTS: { "cat-not-eating": { slug: "cat-not-eating" } },
    publicCheckView: { querySelector: () => node, classList: { add() {} } },
    setPublicCheckGateState() {}, publicCheckResultClass: () => "success", publicCheckResultLabel: () => "Наблюдение",
    storePendingPublicCheckSave: () => stores++, publicCheckSavePayload: () => { throw Error("must preserve saved payload"); },
    escapeHtml: String, formatDateTime: String, formatTriageAnswer: String,
    renderCheckSaveCallout: () => "", renderCheckStickySave: () => "",
    trackFunnel: (name) => events.push(name), getFunnelSessionId: () => "session",
    trackFunnelWhenVisible() {}, scheduleCheckStickySave() {}, revealPublicCheckState() {},
  };
  vm.createContext(ctx);
  vm.runInContext(definition("renderPublicCheckResult") + definition("restorePendingPublicCheckResult"), ctx);
  assert.equal(ctx.restorePendingPublicCheckResult({slug:"dog-vomiting"}), true);
  assert.equal(stores, 0);
  assert.equal(pending.client_request_id, "stable-case");
  assert.deepEqual(events, ["check.result_restored"]);
  assert.ok(node.innerHTML.includes("2026-09-10T10:00:00Z"));
}

{
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(definition("publicCheckSaveRequestPayload"), ctx);
  const request = ctx.publicCheckSaveRequestPayload({
    pet_type: "cat",
    text: "Кошка стала меньше есть",
    answer: "Подробный ответ, который нужно сохранить в истории питомца.",
    urgency: "yellow",
    urgency_label: `Нужна консультация — ${"длинное пояснение ".repeat(10)}`,
    summary: "Нужно наблюдать за состоянием",
    client_request_id: "stable-validation-attempt",
    session_id: "stable-validation-session",
    prompt_tokens: 10,
    completion_tokens: 20,
    total_tokens: 30,
    pet_id: "7",
    create_pet: false,
    has_yclid: true,
    created_at: "2026-09-23T00:00:00Z",
    current_flow_id: "display-only-attribution",
  });
  assert.equal(request.pet_id, 7);
  assert.equal(request.client_request_id, "stable-validation-attempt");
  assert.equal(request.has_yclid, true);
  assert.ok(!("urgency_label" in request));
  assert.ok(!("created_at" in request));
  assert.ok(!("current_flow_id" in request));
}

{
  let pending = { text: "Синтетический случай", answer: "Синтетический ответ", client_request_id: "retry-stable", pet_type: "cat" };
  let petRefreshes = 0;
  const screens = [];
  const element = { addEventListener() {} };
  const ctx = {
    state: { pets: [] }, pendingPublicCheckSave: () => pending, ensureDashboardView() {},
    refreshPets: async () => { if (++petRefreshes > 1) throw Error("dashboard temporarily unavailable"); },
    pendingPublicCheckNeedsPetSelection: () => false,
    storePendingPublicCheckSave: (value) => { pending = value; },
    clearPendingPublicCheckSave: () => { pending = null; },
    setWorkspace: (html) => screens.push(html), trackFunnel() {}, trackServiceGoals() {},
    api: async () => ({ status: "saved", triage_id: 12, pet: { id: 4, pet_name: "Тест" } }),
    refreshAccountState: async () => { throw Error("dashboard refresh failed"); },
    escapeHtml: String, nl2br: String, formatTriageAnswer: String, renderAppIcon: () => "",
    trackMetrikaGoal() {}, attributionEventMetadata: () => ({}),
    setTimeout: (callback) => callback(),
    document: { querySelector: () => element },
  };
  vm.createContext(ctx);
  vm.runInContext(definition("publicCheckSaveRequestPayload") + definition("isTransientCheckSaveError") + definition("withTransientCheckSaveRetry") + definition("completePendingPublicCheckAfterLogin"), ctx);
  assert.equal(await ctx.completePendingPublicCheckAfterLogin(), true);
  assert.equal(pending, null);
  assert.ok(screens.at(-1).includes("Результат сохранён"));
  assert.ok(screens.at(-1).includes("Добавить изменение"));
  assert.ok(!screens.at(-1).includes("Сохранение не завершено"));
}

for (const scenario of ["network", "validation", "pet_limit", "pets_network", "invalid_response", "render_error"]) {
  const attempt = "12345678-1234-1234-1234-123456789abc";
  let pending = { text: "PRIVATE_MEDICAL_CONTENT", answer: "PRIVATE_MEDICAL_CONTENT", client_request_id: attempt, pet_type: "cat" };
  const events = [];
  const screens = [];
  const requests = [];
  const ctx = {
    state: { pets: [] }, pendingPublicCheckSave: () => pending, ensureDashboardView() {},
    refreshPets: async () => { if (scenario === "pets_network") await ctx.api("/api/pets"); },
    pendingPublicCheckNeedsPetSelection: () => false,
    storePendingPublicCheckSave: (value) => { pending = value; }, clearPendingPublicCheckSave: () => { pending = null; },
    setWorkspace: (html) => screens.push(html), trackFunnel: (name, metadata) => events.push({ name, metadata }),
    trackServiceGoals: () => { if (scenario === "render_error") throw Error("PRIVATE_MEDICAL_CONTENT"); },
    refreshAccountState: async () => {}, attributionRequestHeaders: () => ({}),
    escapeHtml: String, readableError: String, renderAppIcon: () => "",
    setTimeout: (callback) => callback(),
    fetch: async (path, options) => {
      requests.push({ path, options });
      if (scenario === "network" || scenario === "pets_network") throw new TypeError("PRIVATE_MEDICAL_CONTENT");
      if (scenario === "validation") return { ok: false, status: 422, json: async () => ({ detail: [{ input: "PRIVATE_MEDICAL_CONTENT" }] }) };
      if (scenario === "pet_limit") return { ok: false, status: 409, json: async () => ({ detail: "pet_limit_reached" }) };
      return { ok: true, status: 200, json: async () => scenario === "invalid_response" ? {} : ({ status: "saved", triage_id: 12, pet: { id: 4 } }) };
    },
  };
  vm.createContext(ctx);
  vm.runInContext(definition("api") + definition("publicCheckSaveRequestPayload") + definition("checkSaveFailureMetadata") + definition("isTransientCheckSaveError") + definition("withTransientCheckSaveRetry") + definition("completePendingPublicCheckAfterLogin"), ctx);
  assert.equal(await ctx.completePendingPublicCheckAfterLogin(), true, scenario);
  const failed = events.filter((event) => event.name === "check.save_failed");
  if (scenario === "render_error") {
    assert.equal(pending, null);
    assert.equal(failed.length, 0);
    assert.ok(screens.at(-1).includes("Результат сохранён"));
    continue;
  }
  assert.equal(pending.client_request_id, attempt, "retry identity survives failure");
  assert.equal(failed.length, 1, scenario);
  const expected = {
    network: ["save_request", 0, "network_error"],
    validation: ["save_request", 422, "validation_error"],
    pet_limit: ["save_request", 409, "pet_limit_reached"],
    pets_network: ["load_pets", 0, "network_error"],
    invalid_response: ["validate_response", 200, "invalid_save_response"],
  }[scenario];
  assert.deepEqual([failed[0].metadata.stage, failed[0].metadata.http_status, failed[0].metadata.error_code], expected);
  assert.equal(failed[0].metadata.attempt_id, attempt);
  assert.ok(!JSON.stringify(events).includes("PRIVATE_MEDICAL_CONTENT"));
  if (scenario !== "pets_network") {
    assert.equal(requests[0].options.headers["X-Tvv-Save-Attempt"], attempt);
    if (scenario === "network" || scenario === "invalid_response") {
      assert.equal(requests[1].options.headers["X-Tvv-Save-Attempt"], attempt);
    }
  }
}

for (const scenario of ["save_network_once", "pets_network_once", "invalid_response_once"]) {
  const attempt = "22345678-1234-1234-1234-123456789abc";
  let pending = { text: "Синтетический случай", answer: "Синтетический ответ", client_request_id: attempt, pet_type: "cat" };
  let petRequests = 0;
  let saveRequests = 0;
  const events = [];
  const ctx = {
    state: { pets: [] }, pendingPublicCheckSave: () => pending, ensureDashboardView() {},
    refreshPets: async () => {
      petRequests += 1;
      if (scenario === "pets_network_once" && petRequests === 1) {
        const error = new Error("offline");
        error.code = "network_error";
        error.httpStatus = 0;
        throw error;
      }
    },
    pendingPublicCheckNeedsPetSelection: () => false,
    storePendingPublicCheckSave: (value) => { pending = value; }, clearPendingPublicCheckSave: () => { pending = null; },
    setWorkspace() {}, trackFunnel: (name, metadata) => events.push({ name, metadata }), trackServiceGoals() {},
    api: async (_path, options) => {
      saveRequests += 1;
      assert.equal(options.headers["X-Tvv-Save-Attempt"], attempt);
      if (scenario === "save_network_once" && saveRequests === 1) {
        const error = new Error("offline");
        error.code = "network_error";
        error.httpStatus = 0;
        throw error;
      }
      if (scenario === "invalid_response_once" && saveRequests === 1) return {};
      return { status: "saved", triage_id: 12, pet: { id: 4, pet_name: "Тест" } };
    },
    refreshAccountState: async () => {}, escapeHtml: String, nl2br: String, formatTriageAnswer: String,
    renderAppIcon: () => "", trackMetrikaGoal() {}, attributionEventMetadata: () => ({}),
    setTimeout: (callback) => callback(), document: { querySelector: () => ({ addEventListener() {} }) },
  };
  vm.createContext(ctx);
  vm.runInContext(definition("publicCheckSaveRequestPayload") + definition("isTransientCheckSaveError") + definition("withTransientCheckSaveRetry") + definition("completePendingPublicCheckAfterLogin"), ctx);
  assert.equal(await ctx.completePendingPublicCheckAfterLogin(), true, scenario);
  assert.equal(pending, null, scenario);
  assert.equal(events.filter((event) => event.name === "check.save_failed").length, 0, scenario);
  // One final refresh follows a confirmed save; the prerequisite refresh is
  // the only operation that should gain an extra retry.
  assert.equal(petRequests, scenario === "pets_network_once" ? 3 : 2, scenario);
  assert.equal(saveRequests, scenario === "save_network_once" || scenario === "invalid_response_once" ? 2 : 1, scenario);
}

{
  const ctx = { renderAdminPageHead: () => "", renderAdminTechnicalDetails: (_title, content) => content, formatDateTime: String };
  vm.createContext(ctx);
  vm.runInContext(["escapeHtml", "adminCell", "renderAdminTable", "renderAdminFunnelPage"].map(definition).join("\n"), ctx);
  const html = ctx.renderAdminFunnelPage({
    conversion_funnel_72h: { save_failures: [{ origin: "server", stage: "validation", http_status: 422,
      error_code: "validation_error", validation_fields: "answer:string_too_long", attempt_id: "<script>" }] },
    funnel_loss_reasons_72h: { save_failed_after_login: 2, save_before_login: 3 },
  });
  assert.ok(html.includes("Диагностика сохранения"));
  assert.ok(html.includes("answer:string_too_long"));
  assert.ok(html.includes("validation_error"));
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(!html.includes("<script>"));
  assert.ok(ctx.renderAdminFunnelPage({}).includes("Ошибки сохранения за 72 часа не зафиксированы"));
}

console.log("Check-save flow: restoration, retries, safe error diagnostics, confirmed-success guards and admin rendering passed");
