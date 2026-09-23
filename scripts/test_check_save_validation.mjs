import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(new URL("../web/app.js", import.meta.url), "utf8");

function definition(name) {
  const marker = new RegExp(`(?:async )?function ${name}\\(`).exec(source);
  assert.ok(marker, `Missing ${name}`);
  const rest = source.slice(marker.index);
  const next = /\n(?:async )?function /.exec(rest);
  return next ? rest.slice(0, next.index) : rest;
}

{
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(definition("publicCheckSaveRequestPayload"), ctx);
  const request = ctx.publicCheckSaveRequestPayload({
    pet_type: "cat",
    text: "Кошка стала меньше есть",
    answer: "Подробный ответ для сохранения в истории питомца.",
    urgency: "yellow",
    urgency_label: `Нужна консультация — ${"длинное пояснение ".repeat(12)}`,
    summary: "Нужно наблюдать за состоянием",
    client_request_id: "stable-save-attempt",
    session_id: "stable-save-session",
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
  assert.equal(request.client_request_id, "stable-save-attempt");
  assert.equal(request.has_yclid, true);
  assert.ok(!("urgency_label" in request));
  assert.ok(!("created_at" in request));
  assert.ok(!("current_flow_id" in request));
}

{
  let calls = 0;
  const ctx = { setTimeout: (callback) => callback() };
  vm.createContext(ctx);
  vm.runInContext(definition("isTransientCheckSaveError") + definition("withTransientCheckSaveRetry"), ctx);
  const result = await ctx.withTransientCheckSaveRetry(async () => {
    calls += 1;
    if (calls === 1) {
      const error = new Error("offline");
      error.code = "network_error";
      error.httpStatus = 0;
      throw error;
    }
    return "saved";
  });
  assert.equal(result, "saved");
  assert.equal(calls, 2);

  calls = 0;
  await assert.rejects(
    ctx.withTransientCheckSaveRetry(async () => {
      calls += 1;
      const error = new Error("validation_error");
      error.code = "validation_error";
      error.httpStatus = 422;
      throw error;
    }),
    /validation_error/,
  );
  assert.equal(calls, 1);
}

{
  const ctx = {
    state: { token: "" },
    attributionRequestHeaders: () => ({}),
    fetch: async () => { throw new TypeError("offline"); },
  };
  vm.createContext(ctx);
  vm.runInContext(definition("api"), ctx);
  await assert.rejects(
    ctx.api("/api/check/preview/save", { method: "POST", body: "{}" }),
    (error) => error.code === "network_error" && error.httpStatus === 0,
  );

  ctx.fetch = async () => ({
    ok: false,
    status: 422,
    json: async () => ({ detail: [{ type: "string_too_long" }] }),
  });
  await assert.rejects(
    ctx.api("/api/check/preview/save", { method: "POST", body: "{}" }),
    (error) => error.code === "validation_error" && error.httpStatus === 422,
  );
}

console.log("check save validation and retry tests ok");
