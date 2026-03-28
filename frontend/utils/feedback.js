const MIN_FEEDBACK_INTERVAL = 180;

function now() {
  return Date.now();
}

function triggerHaptic(page, key = "default") {
  const lastAtMap = (page && page._feedbackLastAtMap) || {};
  const currentAt = now();
  const lastAt = lastAtMap[key] || 0;
  if (currentAt - lastAt < MIN_FEEDBACK_INTERVAL) {
    return;
  }

  if (page) {
    page._feedbackLastAtMap = {
      ...lastAtMap,
      [key]: currentAt
    };
  }

  if (!wx || typeof wx.vibrateShort !== "function") {
    return;
  }

  try {
    wx.vibrateShort();
  } catch (err) {
    // Ignore unsupported haptics.
  }
}

function flashState(page, stateKey, duration = 140) {
  if (!page || typeof page.setData !== "function" || !stateKey) return;

  const timerMap = page._feedbackTimerMap || {};
  if (timerMap[stateKey]) {
    clearTimeout(timerMap[stateKey]);
  }

  page.setData({ [stateKey]: true });
  const timer = setTimeout(() => {
    page.setData({ [stateKey]: false });
    const nextMap = page._feedbackTimerMap || {};
    delete nextMap[stateKey];
    page._feedbackTimerMap = nextMap;
  }, duration);

  page._feedbackTimerMap = {
    ...timerMap,
    [stateKey]: timer
  };
}

function triggerFeedback(page, { hapticKey = "default", flashKey = "", flashDuration = 140 } = {}) {
  triggerHaptic(page, hapticKey);
  if (flashKey) {
    flashState(page, flashKey, flashDuration);
  }
}

module.exports = {
  triggerFeedback
};
