"""Phase 3 TDD tests: Sovereign Sarvam AI Multimodal Suite (Saaras v4, Vision OCR, Bulbul v4/v3)."""
from __future__ import annotations

from pathlib import Path
import unittest

from app.graph.neo4j_client import GraphStoreManager


REPO_ROOT = Path(__file__).resolve().parents[2]


class TestPhase3SarvamSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manager = GraphStoreManager.from_seed_bundle(REPO_ROOT / "data" / "seed_bundle")

    def test_saaras_v4_dual_pass_codemix_and_translate_with_aoi_keyterms(self) -> None:
        from app.sarvam.stt_saaras import SarvamSaarasSttService

        wav_path = REPO_ROOT / "data" / "seed_bundle" / "fixtures" / "velachery_substation_spark.wav"
        self.assertTrue(wav_path.exists())
        service = SarvamSaarasSttService()
        result = service.transcribe_distress_audio(
            audio_bytes=wav_path.read_bytes(),
            aoi_id="chennai",
            language_hint="ta-IN",
            fixture_id="fix-audio-chennai-01",
        )
        self.assertEqual(result.model, "saaras:v4")
        self.assertIn("Velachery", result.codemix_transcript)
        self.assertIn("SUB-CHENNAI-33KV-01", result.english_translation)
        self.assertGreaterEqual(len(result.keyterms_applied), 5)
        self.assertIn("Velachery", result.keyterms_applied)
        self.assertGreater(result.confidence, 0.8)

    def test_sarvam_vision_shelter_register_markdown_table_extraction(self) -> None:
        from app.sarvam.vision_ocr import SarvamVisionOcrService

        service = SarvamVisionOcrService(self.manager)
        ocr_res = service.extract_shelter_register(
            image_bytes=b"FAKE_JPEG_SHELTER_REGISTER_BYTES",
            shelter_node_id="SHEL-CHENNAI-01",
            fixture_id="fix-vision-shelter-ta-01",
        )
        self.assertEqual(ocr_res.model, "sarvam-vision")
        self.assertEqual(ocr_res.shelter_node_id, "SHEL-CHENNAI-01")
        self.assertEqual(len(ocr_res.entries), 1)
        self.assertEqual(ocr_res.total_headcount, 312)
        self.assertEqual(ocr_res.total_medical_needs, 18)

        shelter_node = self.manager.get_node("SHEL-CHENNAI-01")
        self.assertIsNotNone(shelter_node)
        self.assertEqual(shelter_node["current_occupancy"], 312)

    def test_sarvam_vision_flood_signboard_ocr_couples_with_dem_plausibility_gate(self) -> None:
        from app.sarvam.vision_ocr import SarvamVisionOcrService

        service = SarvamVisionOcrService(self.manager)
        coupled = service.extract_signboard_and_gate_sitrep(
            image_bytes=b"FAKE_SIGNBOARD_IMAGE_BYTES",
            report_id="sitrep_ocr_01",
            nearest_node_id="OSM-CHENNAI-008",
            claimed_depth_m=1.25,
            observed_at_iso="2026-10-26T14:40:00Z",
            signboard_text_hint="Velachery Main Rd Subway - Danger Level 1.25m",
            reporter_role="SDRF_RESPONDER",
        )
        self.assertEqual(coupled["ocr_model"], "sarvam-vision")
        self.assertGreater(coupled["plausibility"]["confidence_score"], 0.85)
        self.assertEqual(coupled["plausibility"]["verification_state"], "VERIFIED")

    def test_bulbul_tts_routes_v4_flash_and_v3_fallback_under_latency_budget(self) -> None:
        from app.sarvam.tts_bulbul import SarvamBulbulTtsService

        tts = SarvamBulbulTtsService()
        # Tamil -> bulbul:v4-flash
        res_ta = tts.synthesize_alert(
            text="சைதாப்பேட்டை பாலம் மூடப்பட்டுள்ளது. மாற்றுப் பாதையில் செல்லவும்.",
            language_code="ta-IN",
        )
        self.assertEqual(res_ta.model_used, "bulbul:v4-flash")
        self.assertFalse(res_ta.fallback_triggered)
        self.assertLess(res_ta.latency_ms, 250.0)
        self.assertTrue(res_ta.audio_base64)

        # Malayalam -> automatic fallback to bulbul:v3
        res_ml = tts.synthesize_alert(
            text="വയനാട് ചൂരൽമല പാലം അപകടത്തിലാണ്, സുരക്ഷിത സ്ഥാനത്തേക്ക് മാറുക.",
            language_code="ml-IN",
        )
        self.assertEqual(res_ml.model_used, "bulbul:v3")
        self.assertTrue(res_ml.fallback_triggered)
        self.assertTrue(res_ml.audio_base64)


if __name__ == "__main__":
    unittest.main()
