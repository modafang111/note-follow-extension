"""パイプライン全体で使う例外。予期しない状態では処理を止める。"""

from __future__ import annotations


class PipelineError(Exception):
    """処理を停止する基底例外。"""

    def __init__(self, message: str, stage: str = "") -> None:
        super().__init__(message)
        self.stage = stage
        self.message = message


class ConfigError(PipelineError):
    """設定不備。"""


class SkipPlugin(PipelineError):
    """対象外プラグイン。自動登録しない。"""


class AlreadyProcessed(PipelineError):
    """同一 slug + バージョンが登録済み。"""


class QualityError(PipelineError):
    """翻訳品質の重大エラー。BASEへ登録しない。"""


class NeedHumanReview(PipelineError):
    """CAPTCHA・2FA・画像確認など、人間の確認が必要。"""


class BaseApiUnavailable(PipelineError):
    """BASE公式APIでは実現できない、または認証不足。"""
