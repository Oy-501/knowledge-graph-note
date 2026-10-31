"""本地翻译引擎与标题翻译闸门。"""
import pytest

from app.services import translation_engine as te
from app.services.translate import _BRAND, translate_title

needs_model = pytest.mark.skipif(not te.available(), reason="翻译模型未下载")
slow_model = pytest.mark.slow_model


def test_polish_restores_tech_terms():
    assert te._polish("网络开发指南") == "Web 开发指南"
    assert te._polish("手持门户") == "实战 Portals"
    assert te._polish("什么是DOM?") == "什么是DOM？"


def test_brand_regex_requires_dot():
    """纯小写字母的普通标题曾被误判成域名，整批跳过翻译。"""
    assert _BRAND.match("web.dev")
    assert not _BRAND.match("curatedlistofuistyleguides")
    assert not _BRAND.match("free logos")


def test_override_has_priority_over_model():
    assert translate_title("Free Logos", "design.com") == "免费 Logo 素材"


@needs_model
@slow_model
def test_model_translates_conservative_sentence():
    out = te.translate("The best design resources for new designers")
    assert out and any("\u4e00" <= ch <= "\u9fff" for ch in out)


@needs_model
@slow_model
def test_model_returns_none_for_empty():
    assert te.translate("") is None
