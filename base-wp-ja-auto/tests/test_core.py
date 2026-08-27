"""ユーティリティと抽出器の単体テスト。"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from src.exceptions import PipelineError
from src.plugin_analyzer import _extract_php
from src.translation_builder import quality_check
from src.utils import extract_base_item_id, extract_plugin_slug, placeholders, safe_extract_zip
from src.plugin_analyzer import Message
from src.base_template import _apply_name, _name_template_from_title, TemplateRules


class SlugTests(unittest.TestCase):
    def test_plugin_slug(self) -> None:
        self.assertEqual(
            extract_plugin_slug("https://wordpress.org/plugins/contact-form-7/"),
            "contact-form-7",
        )
        self.assertEqual(
            extract_plugin_slug("https://www.wordpress.org/plugins/wordpress-seo"),
            "wordpress-seo",
        )
        with self.assertRaises(PipelineError):
            extract_plugin_slug("https://example.com/plugins/foo/")

    def test_base_item_id(self) -> None:
        self.assertEqual(extract_base_item_id("12345"), "12345")
        self.assertEqual(extract_base_item_id("https://example.base.shop/items/998877"), "998877")


class ZipSlipTests(unittest.TestCase):
    def test_rejects_traversal(self) -> None:
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "evil.zip"
            dest = Path(tmp) / "out"
            dest.mkdir()
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("../escape.txt", "nope")
            with self.assertRaises(PipelineError):
                safe_extract_zip(
                    zip_path,
                    dest,
                    max_zip_bytes=1024 * 1024,
                    max_files=10,
                    max_file_bytes=1024 * 1024,
                )


class ExtractorTests(unittest.TestCase):
    def test_php_i18n_literals_only(self) -> None:
        source = r'''
        <?php
        echo __( 'Hello', 'demo' );
        _e( "World", 'demo' );
        _x( 'Item', 'context', 'demo' );
        esc_html_e( 'Save', 'demo' );
        echo __( $var, 'demo' );
        echo __( 'A' . $b, 'demo' );
        '''
        messages = _extract_php(source, "demo.php", "demo")
        ids = [m.msgid for m in messages]
        self.assertIn("Hello", ids)
        self.assertIn("World", ids)
        self.assertIn("Item", ids)
        self.assertIn("Save", ids)
        self.assertNotIn("A", ids)


class QualityTests(unittest.TestCase):
    def test_placeholder_mismatch_is_error(self) -> None:
        messages = [Message(msgid="Hello %s", msgctxt="")]
        with TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                quality_check(messages, {("", "Hello %s"): "こんにちは"}, Path(tmp))

    def test_ok_translation(self) -> None:
        messages = [Message(msgid="Hello %s", msgctxt="")]
        with TemporaryDirectory() as tmp:
            report = quality_check(messages, {("", "Hello %s"): "こんにちは %s"}, Path(tmp))
            self.assertEqual(report["error_count"], 0)


class NamingTests(unittest.TestCase):
    def test_name_from_existing_title(self) -> None:
        tmpl = _name_template_from_title("Contact Form 7 WordPressプラグイン 日本語化ファイル", "Contact Form 7")
        self.assertEqual(tmpl, "{plugin_name} WordPressプラグイン 日本語化ファイル")
        rules = TemplateRules(
            source="local",
            item_id="",
            title="",
            detail="",
            price=500,
            stock=10,
            visible=0,
            category_ids=[],
            category_names=[],
            image_urls=[],
            identifier="",
            name_template=tmpl,
            plugin_name_in_template="Contact Form 7",
        )
        self.assertEqual(
            _apply_name(rules, "Hello Dolly"),
            "Hello Dolly WordPressプラグイン 日本語化ファイル",
        )


if __name__ == "__main__":
    unittest.main()
