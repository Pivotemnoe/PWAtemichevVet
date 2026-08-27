import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const appSource = fs.readFileSync(new URL("../web/app.js", import.meta.url), "utf8");
const analyticsStart = appSource.indexOf("const METRIKA_GOALS =");
const analyticsEnd = appSource.indexOf("function normalizeStartupAction");
assert.ok(analyticsStart >= 0 && analyticsEnd > analyticsStart, "analytics block must remain testable");
const analyticsSource = appSource.slice(analyticsStart, analyticsEnd);

class MemoryStorage {
  constructor() {
    this.values = new Map();
  }

  getItem(key) {
    return this.values.has(key) ? this.values.get(key) : null;
  }

  setItem(key, value) {
    this.values.set(key, String(value));
  }

  removeItem(key) {
    this.values.delete(key);
  }
}

let flowSequence = 0;

function loadPage({ href, localStorage, sessionStorage, referrer = "", metrikaReady = true }) {
  const metrikaCalls = [];
  const location = new URL(href);
  const window = {
    location,
    localStorage,
    sessionStorage,
    crypto: { randomUUID: () => `flow-${++flowSequence}` },
    history: { replaceState() {} }
  };
  if (metrikaReady) window.ym = (...args) => metrikaCalls.push(args);
  const context = {
    window,
    document: { referrer },
    localStorage,
    sessionStorage,
    URL,
    URLSearchParams,
    Date,
    Math,
    JSON,
    Object,
    Set,
    String,
    Number,
    Boolean,
    encodeURIComponent,
    fetch: () => Promise.resolve({ ok: true })
  };
  vm.runInNewContext(
    `const METRIKA_ID = 109726654;
     const isAdminRoute = false;
     function getCookieConsent() { return null; }
     ${analyticsSource}
     globalThis.__analytics = {
       attributionEventMetadata,
       attributionRequestHeaders,
       getFunnelSessionId,
       trackMetrikaGoalOnce,
       trackMetrikaGoal,
       flushPendingMetrikaGoals,
       clearPendingMetrikaGoals
     };`,
    context
  );
  return { analytics: context.__analytics, metrikaCalls, window };
}

{
  const page = loadPage({
    href: "https://temichevvet.ru/check/cat-not-eating?utm_source=yandex&utm_campaign=cat-test",
    localStorage: new MemoryStorage(),
    sessionStorage: new MemoryStorage(),
    metrikaReady: false
  });

  assert.equal(page.analytics.trackMetrikaGoal("check.start_click", { slug: "cat-not-eating" }), true);
  assert.equal(page.analytics.trackMetrikaGoal("check.submit", { slug: "cat-not-eating", pet_type: "cat" }), true);
  assert.equal(page.metrikaCalls.length, 0);

  // Consent can initialize Metrika after the first form interactions. Queued goals
  // must keep their original order so result_shown cannot appear without them.
  page.window.ym = (...args) => page.metrikaCalls.push(args);
  assert.equal(page.analytics.flushPendingMetrikaGoals(), true);
  assert.deepEqual(page.metrikaCalls.map((call) => call[2]), ["check_start_click", "check_submit"]);

  page.analytics.trackMetrikaGoal("check.result_shown", { slug: "cat-not-eating", pet_type: "cat" });
  assert.deepEqual(
    page.metrikaCalls.map((call) => call[2]),
    ["check_start_click", "check_submit", "check_result_shown"]
  );
}

function decodedHeader(headers, name) {
  return decodeURIComponent(headers[name] || "");
}

{
  const localStorage = new MemoryStorage();
  const sessionStorage = new MemoryStorage();
  const checkPage = loadPage({
    href: "https://temichevvet.ru/check?utm_source=yandex&utm_medium=cpc&utm_campaign=check-campaign&yclid=first-click",
    localStorage,
    sessionStorage
  });
  const check = checkPage.analytics.attributionEventMetadata();

  const petPage = loadPage({
    href: "https://temichevvet.ru/pet?utm_source=yandex&utm_medium=cpc&utm_campaign=pet-campaign&yclid=second-click",
    localStorage,
    sessionStorage
  });
  const pet = petPage.analytics.attributionEventMetadata();
  const headers = petPage.analytics.attributionRequestHeaders();

  assert.equal(check.first_landing_path, "/check");
  assert.equal(check.current_landing_path, "/check");
  assert.equal(pet.first_landing_path, "/check");
  assert.equal(pet.first_utm_campaign, "check-campaign");
  assert.equal(pet.current_landing_path, "/pet");
  assert.equal(pet.current_utm_campaign, "pet-campaign");
  assert.notEqual(pet.current_flow_id, check.current_flow_id);
  assert.equal(decodedHeader(headers, "X-Tvv-Landing-Path"), "/pet");
  assert.equal(decodedHeader(headers, "X-Tvv-Utm-Campaign"), "pet-campaign");
  assert.equal(decodedHeader(headers, "X-Tvv-First-Landing-Path"), "/check");
  assert.equal(decodedHeader(headers, "X-Tvv-First-Utm-Campaign"), "check-campaign");
  assert.equal(decodedHeader(headers, "X-Tvv-Funnel-Session"), pet.current_flow_id);
}

{
  const localStorage = new MemoryStorage();
  const sessionStorage = new MemoryStorage();
  const foodPage = loadPage({ href: "https://temichevvet.ru/food/dog", localStorage, sessionStorage });
  const food = foodPage.analytics.attributionEventMetadata();
  const petPage = loadPage({ href: "https://temichevvet.ru/pet", localStorage, sessionStorage });
  const pet = petPage.analytics.attributionEventMetadata();
  const cabinetPage = loadPage({ href: "https://temichevvet.ru/app", localStorage, sessionStorage });
  const cabinet = cabinetPage.analytics.attributionEventMetadata();

  assert.equal(pet.first_landing_path, "/food/dog");
  assert.equal(pet.current_landing_path, "/pet");
  assert.notEqual(pet.current_flow_id, food.current_flow_id);
  assert.equal(cabinet.current_landing_path, "/pet");
  assert.equal(cabinet.current_flow_id, pet.current_flow_id);
}

{
  const page = loadPage({
    href: "https://temichevvet.ru/pet?utm_source=yandex&utm_campaign=pet-created",
    localStorage: new MemoryStorage(),
    sessionStorage: new MemoryStorage()
  });
  const metadata = { ...page.analytics.attributionEventMetadata(), pet_type: "cat", has_pet: true, secret: "drop-me" };

  assert.equal(page.analytics.trackMetrikaGoalOnce("pet.created", "pet:42", metadata), true);
  assert.equal(page.analytics.trackMetrikaGoalOnce("pet.created", "pet:42", metadata), false);
  assert.equal(page.metrikaCalls.length, 1);
  assert.equal(page.metrikaCalls[0][2], "pet_created");
  assert.equal(page.metrikaCalls[0][3].current_landing_path, "/pet");
  assert.equal(page.metrikaCalls[0][3].secret, undefined);
}

console.log("frontend attribution tests ok");
