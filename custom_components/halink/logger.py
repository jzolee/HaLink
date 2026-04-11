import logging
import difflib
from collections import deque
from time import monotonic

class DedupLogger:
    """
    Smart deduplicating logger.
    - Keeps history of recent messages.
    - Detects similarity instead of strict equality.
    - Demotes repeated messages to DEBUG level (for traceability).
    """

    def __init__(
        self,
        logger: logging.Logger | None = None,
        name: str | None = None,
        *,
        max_history: int = 100,
        similarity: float = 0.85,
        cooldown: float = 0.0,
    ):
        """
        Args:
            logger: Existing logger instance, or None to create new.
            name: Logger name if creating new.
            max_history: Number of recent messages remembered.
            similarity: 0.0-1.0 threshold; above means "similar".
            cooldown: Optional time window (sec) before repeating same message again at full level.
        """
        self._logger = logger or logging.getLogger(name or __name__)
        self._history = deque(maxlen=max_history)
        self._similarity = similarity
        self._cooldown = cooldown
        self._last_time: dict[str, float] = {}

    # ------------------------------------------------------------------
    def _is_recent_similar(self, message: str) -> bool:
        """Check if a similar message has been logged recently."""
        for old in self._history:
            ratio = difflib.SequenceMatcher(None, old, message).ratio()
            if ratio >= self._similarity:
                return True
        return False

    def _should_demote(self, message: str, level_name: str) -> bool:
        """Return True if this message should be demoted to debug."""
        if not self._is_recent_similar(message):
            return False

        # Optional cooldown check
        now = monotonic()
        key = f"{level_name}:{message[:50]}"  # short key
        last = self._last_time.get(key, 0)
        if self._cooldown and (now - last) < self._cooldown:
            return True
        self._last_time[key] = now
        return True

    def _log(self, level_func, level_name: str, message: str, *args, **kwargs):
        """Central logging logic with similarity and demotion."""
        try:
            if self._should_demote(message, level_name):
                self._logger.debug(f"[dedup→{level_name}] {message}", *args, **kwargs)
            else:
                self._history.append(message)
                level_func(message, *args, **kwargs)
        except Exception as e:
            # Defensive: logger should never raise
            self._logger.error(f"DedupLogger internal error: {e}")

    # ------------------------------------------------------------------
    def warning(self, message, *args, **kwargs):
        self._log(self._logger.warning, "warning", str(message), *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self._log(self._logger.error, "error", str(message), *args, **kwargs)

    def info(self, message, *args, **kwargs):
        self._log(self._logger.info, "info", str(message), *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        self._logger.debug(str(message), *args, **kwargs)

    # ------------------------------------------------------------------
    def reset(self):
        """Clear history and cooldown memory."""
        self._history.clear()
        self._last_time.clear()

    @property
    def logger(self):
        """Underlying logger."""
        return self._logger
