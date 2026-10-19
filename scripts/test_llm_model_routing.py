"""Provider request contracts. The fake client prevents live API calls."""
import hashlib
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import llm_triage


class LlmModelRoutingTests(unittest.TestCase):
    def request_for(self, model, plan, answer='2) Уровень срочности: 🟡 Нужна консультация — свяжитесь с врачом.'):
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=answer))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )))))
        environment = {'OPENAI_API_KEY': 'fixture-key', 'OPENAI_BASE_URL': 'http://127.0.0.1:8091/v1', 'OPENAI_MODEL': model,
                       'OPENAI_MODEL_FREE': model, 'OPENAI_MODEL_PLUS': model}
        constructor = Mock(return_value=client)
        provider = ModuleType('openai')
        provider.OpenAI = constructor
        with patch.dict(os.environ, environment, clear=True), patch.dict(sys.modules, {'openai': provider}):
            result = llm_triage.call_triage_llm(user={'name': 'QA'}, pets=[], selected_pet=None,
                complaint_text='Синтетический пример', plan_code=plan)
        return client.chat.completions.create.call_args.kwargs, constructor.call_args.kwargs, result

    def test_free_luna_keeps_non_reasoning_latency_and_sampling(self):
        request, _, result = self.request_for('gpt-6-luna', 'free')
        self.assertEqual(request['reasoning_effort'], 'none')
        self.assertEqual(request['temperature'], 1)
        self.assertNotIn(llm_triage.PLUS_EXPERT_ADDON.strip(), request['messages'][0]['content'])
        self.assertEqual(result.model, 'gpt-6-luna')

    def test_plus_luna_uses_reasoning_without_unsupported_sampling(self):
        request, _, _ = self.request_for('gpt-6-luna', 'plus')
        self.assertEqual(request['reasoning_effort'], 'medium')
        self.assertNotIn('temperature', request)
        self.assertIn(llm_triage.PLUS_EXPERT_ADDON.strip(), request['messages'][0]['content'])
        self.assertIn(llm_triage.PLUS_FOLLOWUP_ADDON.strip(), request['messages'][0]['content'])

    def test_plus_prompt_update_preserves_other_tier_prompts(self):
        # Golden hashes captured before the Plus change protect the other live tiers.
        for plan, expected in [
            ('free', '2ba9b1ac6a2fad5a0e8a241908234f2e63a5629b118f409815e9b026edfc06c4'),
            ('pro', '9f458b07369770eaf5bf58acee2b63432a8fc858036b7276e8de07727d1396bb'),
            ('vip', '9f458b07369770eaf5bf58acee2b63432a8fc858036b7276e8de07727d1396bb'),
        ]:
            with self.subTest(plan=plan):
                self.assertEqual(hashlib.sha256(llm_triage._system_prompt_for_plan(plan).encode()).hexdigest(), expected)

    def test_plan_case_and_snapshot_use_the_same_request_contract(self):
        request, _, _ = self.request_for('gpt-6-luna-2026-10-01', ' PLUS ')
        self.assertEqual(request['reasoning_effort'], 'medium')
        self.assertNotIn('temperature', request)

    def test_legacy_free_and_plus_parameters_are_preserved(self):
        for model, plan in [('gpt-4.1-mini', 'free'), ('gpt-5-mini', 'plus')]:
            with self.subTest(model=model):
                request, _, _ = self.request_for(model, plan)
                self.assertEqual(request['temperature'], 1)
                self.assertNotIn('reasoning_effort', request)

    def test_existing_explicit_model_routes_and_pinned_legacy_tiers_remain(self):
        with patch.dict(os.environ, {'OPENAI_MODEL': 'fallback', 'OPENAI_MODEL_FREE': 'free-model',
                'OPENAI_MODEL_PLUS': 'plus-model', 'OPENAI_MODEL_PRO': 'pinned-pro', 'OPENAI_MODEL_VIP': 'pinned-vip'}, clear=True):
            for plan, model in [('free', 'free-model'), ('plus', 'plus-model'), ('pro', 'pinned-pro'), ('vip', 'pinned-vip'), ('unknown', 'fallback')]:
                self.assertEqual(llm_triage._model_for_plan(plan), model)

    def test_unconfigured_fallback_uses_current_efficient_model(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(llm_triage._model_for_plan('free'), 'gpt-6-luna')
            self.assertEqual(llm_triage._model_for_plan('plus'), 'gpt-6-luna')

    def test_gateway_timeout_usage_and_normalization_are_preserved(self):
        _, constructor, result = self.request_for('gpt-6-luna', 'plus')
        self.assertEqual(constructor['base_url'], 'http://127.0.0.1:8091/v1')
        self.assertEqual(constructor['timeout'], 45.0)
        self.assertEqual((result.prompt_tokens, result.completion_tokens, result.total_tokens), (100, 50, 150))
        self.assertIn(llm_triage.TRUST_PHRASE, result.text)

    def test_plus_emphasized_urgency_is_parseable_without_changing_the_level(self):
        for markup in ['**', '__']:
            for level, emoji, label in [('green', '🟢', 'Можно наблюдать'), ('yellow', '🟡', 'Нужна консультация'), ('red', '🟥', 'Срочно в клинику')]:
                with self.subTest(markup=markup, level=level):
                    answer = f'1) Кратко: тест.\n\n2) {markup}Уровень срочности: {emoji} {label} —{markup} пояснение.\n\n3) План.'
                    _, _, result = self.request_for('gpt-6-luna', 'plus', answer)
                    self.assertEqual(llm_triage.extract_urgency(result.text)[2], level)
                    self.assertIn('пояснение.', result.text)
        _, _, free = self.request_for('gpt-6-luna', 'free', answer)
        self.assertIn(markup, free.text)

    def test_missing_key_does_not_call_provider(self):
        constructor = Mock()
        provider = ModuleType('openai')
        provider.OpenAI = constructor
        with patch.dict(os.environ, {}, clear=True), patch.dict(sys.modules, {'openai': provider}):
            with self.assertRaisesRegex(RuntimeError, 'openai_not_configured'):
                llm_triage.call_triage_llm(user={}, pets=[], selected_pet=None, complaint_text='QA', plan_code='free')
            constructor.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
