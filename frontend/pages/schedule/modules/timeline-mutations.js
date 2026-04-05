const { getDataVersion, markDataDirty } = require("../../../utils/data-sync");

function nextTickAsync() {
  return new Promise((resolve) => {
    wx.nextTick(resolve);
  });
}

function triggerTimelineSettle(page) {
  if (page._timelineSettleTimer) {
    clearTimeout(page._timelineSettleTimer);
  }
  page.setData({ timelineSettleActive: true });
  page._timelineSettleTimer = setTimeout(() => {
    page._timelineSettleTimer = null;
    page.setData({ timelineSettleActive: false });
  }, 260);
}

function resolveMutationFocusDay(options = {}) {
  if (options.focusDayKey) {
    return options.focusDayKey;
  }
  if (options.focusEntry && options.focusEntry.dayKey) {
    return options.focusEntry.dayKey;
  }
  return "";
}

async function remountTimelineView(page, options = {}) {
  page.setData({
    timelineMounted: false,
    activeStickyDay: null
  });
  await nextTickAsync();
  page.setData({
    timelineMounted: true,
    activeStickyDay: null
  });
  await nextTickAsync();
  page.rebuildStickyDayAnchors();
  triggerTimelineSettle(page);
  const focusDayKey = resolveMutationFocusDay(options);
  if (!focusDayKey) return;
  const visibleDays = page.data.visibleDays || [];
  const targetDayKey = visibleDays.some((day) => day.day_key === focusDayKey)
    ? focusDayKey
    : page.resolveNearestTimelineDayKey(focusDayKey, visibleDays);
  if (!targetDayKey) return;
  setTimeout(() => {
    page.scrollToDay(targetDayKey, { duration: 160, silent: true });
  }, 24);
}

async function settleTimelineAfterMutation(page, options = {}) {
  await nextTickAsync();
  await remountTimelineView(page, options);
}

function removeTimelineEntriesLocally(page, entries = [], options = {}) {
  const familyKeys = new Set(
    (entries || [])
      .filter(Boolean)
      .map((item) => `${item.kind}-${item.source_id}`)
  );
  if (!familyKeys.size) return;

  const nextDays = (page.data.days || [])
    .map((day) => ({
      ...day,
      items: (day.items || []).filter((item) => !familyKeys.has(`${item.kind}-${item.source_id}`))
    }))
    .filter((day) => Array.isArray(day.items) && day.items.length);

  const nextSelected = options.clearSelection ? [] : (page.data.selectedItemKeys || []);
  page.daySectionAnchors = [];
  page.setData({
    days: nextDays,
    selectedItemKeys: nextSelected,
    multiSelectMode: options.clearSelection ? false : page.data.multiSelectMode,
    visibleDays: page.applySelectionState(page.buildVisibleDays(nextDays, page.data.activeKindFilter), nextSelected),
    activeStickyDay: null
  }, () => {
    page.rebuildStickyDayAnchors();
    triggerTimelineSettle(page);
  });
}

function removeDeletedItemLocally(page, editingId, composerKind) {
  const targetId = `${editingId || ""}`;
  if (!targetId) return;
  let matchedEntry = null;
  (page.data.visibleDays || []).some((day) => {
    const found = (day.items || []).find((item) => (
      `${item.source_id || ""}` === targetId &&
      (composerKind === "schedule" ? item.kind === "schedule" : item.kind !== "schedule")
    ));
    if (!found) return false;
    matchedEntry = found;
    return true;
  });
  if (!matchedEntry) return;
  removeTimelineEntriesLocally(page, [matchedEntry]);
}

async function afterMutation(page, teamId, scopes, options = {}) {
  markDataDirty({ teamId, scopes });
  await Promise.all([
    page.loadTimeline(teamId),
    page.loadCommonCategories(teamId),
    page.loadPlaceSuggestions(teamId, "")
  ]);
  page.setData({
    scheduleSyncVersion: getDataVersion("schedule", teamId),
    financeSyncVersion: getDataVersion("finance", teamId)
  });
  await settleTimelineAfterMutation(page, options);
}

module.exports = {
  afterMutation,
  nextTickAsync,
  remountTimelineView,
  removeDeletedItemLocally,
  removeTimelineEntriesLocally,
  resolveMutationFocusDay,
  settleTimelineAfterMutation,
  triggerTimelineSettle
};
