const { bootstrapSession, getCurrentTeamState } = require("../../utils/bootstrap");
const { applyPageLocale, translateMessage } = require("../../utils/i18n");
const { getDataVersion } = require("../../utils/data-sync");
const { triggerFeedback } = require("../../utils/feedback");
const scheduleApi = require("./modules/api");
const {
  buildFinancePayload,
  buildSchedulePayload
} = require("./modules/composer");
const {
  buildComposerClosedState,
  buildFinanceCreateComposerState,
  buildFinanceDuplicateComposerState,
  buildFinanceEditComposerState,
  buildScheduleCreateComposerState,
  buildScheduleDuplicateComposerState,
  buildScheduleEditComposerState
} = require("./modules/composer-state");
const {
  confirmDeleteEditing,
  submitComposer
} = require("./modules/mutations");
const {
  addDays,
  buildCategorySuggestions,
  buildEmptyFinanceForm,
  buildEmptyScheduleForm,
  formatDate,
  toWindowEndIso,
  toWindowStartIso
} = require("./modules/state");
const {
  buildCalendarWeeks,
  buildVisibleDays,
  monthStartFromKey
} = require("./modules/timeline");
const {
  afterMutation: runAfterMutation,
  nextTickAsync,
  remountTimelineView,
  removeDeletedItemLocally,
  removeTimelineEntriesLocally,
  resolveMutationFocusDay,
  settleTimelineAfterMutation,
  triggerTimelineSettle
} = require("./modules/timeline-mutations");
const {
  buildSwipeMoveState,
  closeSwipeRows,
  resolveSwipeEnd
} = require("./modules/swipe");

const COPY_BUTTON_WIDTH = 88;
const EDIT_BUTTON_WIDTH = 88;
const HARD_ACTION_THRESHOLD = 160;
const MAX_SWIPE = 220;
const SWIPE_LAZINESS = 54;
const DIRECTION_LOCK_THRESHOLD = 12;
const PAST_WINDOW_DAYS = 120;
const FUTURE_WINDOW_DAYS = 90;
const DAY_RAIL_STICKY_TOP_RPX = 132;
const DAY_RAIL_STICKY_GAP_RPX = 8;
const MAX_COMPACT_SUGGESTIONS = 7;

Page({
  data: {
    loading: false,
    teams: [],
    teamIndex: 0,
    hasTeam: true,
    teamReady: false,
    currentTeamId: "",
    scheduleSyncVersion: 0,
    financeSyncVersion: 0,
    days: [],
    visibleDays: [],
    activeKindFilter: "",
    activeStickyDay: null,
    stickyDayFeedbackActive: false,
    initialScrollDone: false,
    isQuickCreateOpen: false,
    isFilterOpen: false,
    calendarOpen: false,
    calendarTitle: "",
    calendarWeeks: [],
    calendarMonthKey: "",
    calendarAnchorDay: "",
    calendarMaxCount: 0,
    composerOpen: false,
    composerKind: "schedule",
    composerMode: "create",
    editingId: "",
    scheduleForm: buildEmptyScheduleForm(),
    financeForm: buildEmptyFinanceForm(),
    placeSuggestions: [],
    compactPlaceSuggestions: [],
    commonCategories: [],
    categorySuggestions: [],
    compactCategorySuggestions: [],
    swipeStartX: 0,
    swipeStartY: 0,
    swipeDirection: "",
    multiSelectMode: false,
    selectedItemKeys: [],
    timelineMounted: true,
    timelineSettleActive: false,
    locale: "zh-CN",
    i18n: {
      app: {},
      common: {},
      page: {},
      chart: {}
    }
  },

  onLoad() {
    this.pendingTimelineAnchor = null;
    this.measuredStickyTop = this.rpxToPx(DAY_RAIL_STICKY_TOP_RPX + DAY_RAIL_STICKY_GAP_RPX);
  },

  rpxToPx(value) {
    const info = typeof wx.getWindowInfo === "function"
      ? wx.getWindowInfo()
      : wx.getSystemInfoSync();
    const windowWidth = (info && info.windowWidth) || 375;
    return Math.round((Number(value) || 0) * windowWidth / 750);
  },

  onPageScroll(event) {
    this.refreshStickyDay(event && typeof event.scrollTop === "number" ? event.scrollTop : 0);
  },

  async onShow() {
    this.applyLocale();
    const { teamId } = getCurrentTeamState();
    if (!this.data.teamReady || this.data.currentTeamId !== teamId) {
      await this.initPage();
      return;
    }
    const financeVersion = getDataVersion("finance", teamId);
    const scheduleVersion = getDataVersion("schedule", teamId);
    if (
      financeVersion > (this.data.financeSyncVersion || 0) ||
      scheduleVersion > (this.data.scheduleSyncVersion || 0)
    ) {
      this.setData({ loading: true });
      try {
        await Promise.all([
          this.loadTimeline(teamId),
          this.loadCommonCategories(teamId),
          this.loadPlaceSuggestions(teamId, "")
        ]);
        this.setData({
          financeSyncVersion: financeVersion,
          scheduleSyncVersion: scheduleVersion
        });
      } catch (err) {
        wx.showToast({ title: this.t("common.loadFailed"), icon: "none" });
      } finally {
        this.setData({ loading: false });
      }
    }
  },

  applyLocale() {
    const categorySuggestions = this.buildCategorySuggestions(
      this.data.financeForm.category,
      this.data.financeForm.type
    );
    applyPageLocale(this, "schedule");
    this.setData({
      visibleDays: this.applySelectionState(this.buildVisibleDays(this.data.days, this.data.activeKindFilter)),
      categorySuggestions,
      compactCategorySuggestions: this.limitCompactSuggestions(categorySuggestions),
      activeStickyDay: null
    }, () => {
      this.rebuildStickyDayAnchors();
    });
  },

  t(path, params = {}) {
    return translateMessage(this.data.i18n, path, params);
  },

  async initPage() {
    this.setData({ loading: true });
    try {
      const { teamId, teams } = await bootstrapSession();
      const today = formatDate(new Date());
      this.setData({
        teams,
        hasTeam: !!teamId,
        teamReady: true,
        currentTeamId: teamId,
        scheduleSyncVersion: 0,
        financeSyncVersion: 0,
        activeKindFilter: "",
        activeStickyDay: null,
        stickyDayFeedbackActive: false,
        days: [],
        visibleDays: [],
        initialScrollDone: false,
        isQuickCreateOpen: false,
        isFilterOpen: false,
        calendarOpen: false,
        calendarTitle: "",
        calendarWeeks: [],
        calendarMonthKey: "",
        calendarAnchorDay: "",
        calendarMaxCount: 0,
        composerOpen: false,
        composerKind: "schedule",
        composerMode: "create",
        editingId: "",
        scheduleForm: buildEmptyScheduleForm(today),
        financeForm: buildEmptyFinanceForm(new Date()),
        placeSuggestions: [],
        compactPlaceSuggestions: [],
        commonCategories: [],
        categorySuggestions: [],
        compactCategorySuggestions: []
      });
      if (!teamId) {
        this.daySectionAnchors = [];
        return;
      }
      const teamIndex = Math.max(0, teams.findIndex((item) => item.id === teamId));
      this.setData({ teamIndex });
      await Promise.all([
        this.loadTimeline(teamId),
        this.loadCommonCategories(teamId),
        this.loadPlaceSuggestions(teamId, "")
      ]);
      this.setData({
        financeSyncVersion: getDataVersion("finance", teamId),
        scheduleSyncVersion: getDataVersion("schedule", teamId)
      });
    } catch (err) {
      wx.showToast({ title: this.t("common.initFailed"), icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  currentTeam() {
    return this.data.teams[this.data.teamIndex] || null;
  },

  currentTeamReadonly() {
    const team = this.currentTeam();
    return !!(team && team.is_readonly);
  },

  showReadonlyTip() {
    wx.showToast({ title: this.t("page.readonlyTip"), icon: "none" });
  },

  buildCalendarWeeks(monthKey, anchorDay) {
    return buildCalendarWeeks({
      monthKey,
      anchorDay,
      days: this.data.days
    });
  },

  buildVisibleDays(days = this.data.days, activeKindFilter = this.data.activeKindFilter) {
    return buildVisibleDays({
      days,
      activeKindFilter,
      t: this.t.bind(this)
    });
  },

  async loadTimeline(teamId) {
    const windowStart = toWindowStartIso(addDays(new Date(), -PAST_WINDOW_DAYS));
    const windowEnd = toWindowEndIso(addDays(new Date(), FUTURE_WINDOW_DAYS));
    const data = await scheduleApi.listTimeline(teamId, { windowStart, windowEnd });
    const days = Array.isArray(data && data.days) ? data.days : [];
    this.setData({
      days,
      visibleDays: this.applySelectionState(this.buildVisibleDays(days, this.data.activeKindFilter)),
      activeStickyDay: null
    });
    wx.nextTick(() => {
      this.rebuildStickyDayAnchors();
      this.scrollToTodayAnchor();
    });
  },

  async loadCommonCategories(teamId) {
    const categories = await scheduleApi.listFinanceCategories(teamId);
    const categorySuggestions = this.buildCategorySuggestions(
      this.data.financeForm.category,
      this.data.financeForm.type
    );
    this.setData({
      commonCategories: Array.isArray(categories) ? categories : [],
      categorySuggestions,
      compactCategorySuggestions: this.limitCompactSuggestions(categorySuggestions)
    });
  },

  async loadPlaceSuggestions(teamId, query) {
    if (!teamId) return;
    try {
      const places = await scheduleApi.listPlaces(teamId, query);
      const nextPlaces = Array.isArray(places) ? places : [];
      this.setData({
        placeSuggestions: nextPlaces,
        compactPlaceSuggestions: this.limitCompactSuggestions(nextPlaces)
      });
    } catch (err) {
      this.setData({ placeSuggestions: [], compactPlaceSuggestions: [] });
    }
  },

  limitCompactSuggestions(items = []) {
    return (items || []).slice(0, MAX_COMPACT_SUGGESTIONS);
  },

  presetCategories(type) {
    const page = this.data.i18n.page || {};
    const source = type === "income" ? page.incomePresets : page.expensePresets;
    return Array.isArray(source) ? source.slice() : [];
  },

  buildCategorySuggestions(query, type) {
    return buildCategorySuggestions({
      query,
      presets: this.presetCategories(type),
      commonCategories: this.data.commonCategories || []
    });
  },

  dayKeyToTime(dayKey) {
    const time = new Date(`${dayKey || ""}T00:00:00`).getTime();
    return Number.isFinite(time) ? time : 0;
  },

  resolveTimelineAnchorDays() {
    return this.data.visibleDays || [];
  },

  resolveNearestTimelineDayKey(targetDayKey, days) {
    if (!Array.isArray(days) || !days.length) return "";
    const targetTime = this.dayKeyToTime(targetDayKey);
    let nearestDayKey = days[0].day_key;
    let nearestDistance = Infinity;
    let nearestDelta = Infinity;

    days.forEach((day) => {
      const dayTime = this.dayKeyToTime(day.day_key);
      const delta = dayTime - targetTime;
      const distance = Math.abs(delta);
      const shouldReplace = distance < nearestDistance || (
        distance === nearestDistance &&
        ((nearestDelta < 0 && delta >= 0) || (nearestDelta >= 0 && delta >= 0 && delta < nearestDelta))
      );
      if (!shouldReplace) return;
      nearestDayKey = day.day_key;
      nearestDistance = distance;
      nearestDelta = delta;
    });

    return nearestDayKey;
  },

  getTodayAnchorId() {
    const today = formatDate(new Date());
    const anchorDays = this.resolveTimelineAnchorDays();
    if (!anchorDays.length) return "";
    const exact = anchorDays.find((day) => day.day_key === today);
    const dayKey = exact ? exact.day_key : this.resolveNearestTimelineDayKey(today, anchorDays);
    return dayKey ? `day-${dayKey}` : "";
  },

  getStickyTopOffset() {
    return this.measuredStickyTop || this.rpxToPx(DAY_RAIL_STICKY_TOP_RPX + DAY_RAIL_STICKY_GAP_RPX);
  },

  measureStickyTopOffset() {
    return new Promise((resolve) => {
      const fallback = this.rpxToPx(DAY_RAIL_STICKY_TOP_RPX + DAY_RAIL_STICKY_GAP_RPX);
      const query = wx.createSelectorQuery();
      query.select(".day-rail-floating").boundingClientRect();
      query.select(".sticky-stack").boundingClientRect();
      query.exec((res) => {
        const floatingRect = Array.isArray(res) ? res[0] : null;
        const stickyRect = Array.isArray(res) ? res[1] : null;
        if (floatingRect && typeof floatingRect.top === "number") {
          this.measuredStickyTop = Math.max(Math.round(floatingRect.top), fallback);
          resolve(this.measuredStickyTop);
          return;
        }
        if (stickyRect && typeof stickyRect.height === "number") {
          this.measuredStickyTop = Math.max(Math.round(stickyRect.height + this.rpxToPx(DAY_RAIL_STICKY_GAP_RPX)), fallback);
          resolve(this.measuredStickyTop);
          return;
        }
        this.measuredStickyTop = fallback;
        resolve(this.measuredStickyTop);
      });
    });
  },

  scrollToTodayAnchor() {
    if (this.data.initialScrollDone) return;
    const anchorId = this.getTodayAnchorId();
    if (!anchorId) return;
    this.measureStickyTopOffset().then(() => {
      const query = wx.createSelectorQuery();
      query.select(`#${anchorId}`).boundingClientRect();
      query.selectViewport().scrollOffset();
      query.exec((res) => {
        const rect = res && res[0];
        const viewport = res && res[1];
        if (!rect || !viewport) return;
        const top = Math.max((viewport.scrollTop || 0) + rect.top - this.getStickyTopOffset(), 0);
        wx.pageScrollTo({ scrollTop: top, duration: 0 });
        this.setData({ initialScrollDone: true });
        this.refreshStickyDay(top);
      });
    });
  },

  backToToday() {
    this.setData({ initialScrollDone: false });
    wx.nextTick(() => this.scrollToTodayAnchor());
  },

  openCalendar(event) {
    const dayKey = (event.currentTarget.dataset.dayKey || this.getTodayAnchorId().replace("day-", "") || formatDate(new Date()));
    const next = this.buildCalendarWeeks(dayKey, dayKey);
    this.setData({
      calendarOpen: true,
      calendarTitle: next.title,
      calendarWeeks: next.weeks,
      calendarMonthKey: next.monthKey,
      calendarAnchorDay: dayKey,
      calendarMaxCount: next.maxCount,
      isQuickCreateOpen: false,
      isFilterOpen: false
    });
  },

  closeCalendar() {
    this.setData({
      calendarOpen: false
    });
  },

  shiftCalendarMonth(event) {
    const direction = Number(event.currentTarget.dataset.direction || 0);
    const base = monthStartFromKey(this.data.calendarMonthKey || formatDate(new Date()));
    base.setMonth(base.getMonth() + direction);
    const next = this.buildCalendarWeeks(formatDate(base), this.data.calendarAnchorDay);
    this.setData({
      calendarTitle: next.title,
      calendarWeeks: next.weeks,
      calendarMonthKey: next.monthKey,
      calendarMaxCount: next.maxCount
    });
  },

  onPickCalendarDay(event) {
    const dayKey = event.currentTarget.dataset.dayKey;
    if (!dayKey) return;
    this.setData({
      calendarAnchorDay: dayKey,
      calendarOpen: false
    });
    wx.nextTick(() => this.scrollToDay(dayKey));
  },

  scrollToDay(dayKey, options = {}) {
    const duration = typeof options.duration === "number" ? options.duration : 220;
    const silent = !!options.silent;
    const anchorId = `day-${dayKey}`;
    this.measureStickyTopOffset().then(() => {
      const query = wx.createSelectorQuery();
      query.select(`#${anchorId}`).boundingClientRect();
      query.selectViewport().scrollOffset();
      query.exec((res) => {
        const rect = res && res[0];
        const viewport = res && res[1];
        if (!rect || !viewport) {
          if (!silent) {
            wx.showToast({ title: this.t("page.dayNotLoaded"), icon: "none" });
          }
          return;
        }
        const top = Math.max((viewport.scrollTop || 0) + rect.top - this.getStickyTopOffset(), 0);
        wx.pageScrollTo({ scrollTop: top, duration });
        this.refreshStickyDay(top);
      });
    });
  },

  nextTickAsync() {
    return nextTickAsync();
  },

  triggerTimelineSettle() {
    triggerTimelineSettle(this);
  },

  async remountTimelineView(options = {}) {
    await remountTimelineView(this, options);
  },

  resolveMutationFocusDay(options = {}) {
    return resolveMutationFocusDay(options);
  },

  async settleTimelineAfterMutation(options = {}) {
    await settleTimelineAfterMutation(this, options);
  },

  removeTimelineEntriesLocally(entries = [], options = {}) {
    removeTimelineEntriesLocally(this, entries, options);
  },

  rebuildStickyDayAnchors() {
    const visibleDays = this.data.visibleDays || [];
    if (!visibleDays.length) {
      this.daySectionAnchors = [];
      if (this.data.activeStickyDay) {
        this.setData({ activeStickyDay: null });
      }
      return;
    }

    const query = wx.createSelectorQuery();
    visibleDays.forEach((day) => {
      query.select(`#day-${day.day_key}`).boundingClientRect();
    });
    query.selectViewport().scrollOffset();
    query.exec((res) => {
      if (!Array.isArray(res) || !res.length) return;
      const viewport = res[res.length - 1] || {};
      const scrollTop = viewport.scrollTop || 0;
      const rects = res.slice(0, visibleDays.length);
      this.daySectionAnchors = rects
        .map((rect, index) => {
          if (!rect) return null;
          return {
            dayKey: visibleDays[index].day_key,
            top: scrollTop + rect.top
          };
        })
        .filter(Boolean);
      this.refreshStickyDay(scrollTop);
    });
  },

  refreshStickyDay(scrollTop = 0) {
    const anchors = this.daySectionAnchors || [];
    const visibleDays = this.data.visibleDays || [];
    if (!anchors.length || !visibleDays.length) {
      if (this.data.activeStickyDay) {
        this.setData({ activeStickyDay: null });
      }
      return;
    }

    const targetTop = scrollTop + this.getStickyTopOffset() + 1;
    let activeKey = anchors[0].dayKey;
    for (let index = 0; index < anchors.length; index += 1) {
      if (anchors[index].top <= targetTop) {
        activeKey = anchors[index].dayKey;
        continue;
      }
      break;
    }

    const current = this.data.activeStickyDay;
    if (current && current.day_key === activeKey) {
      return;
    }
    const activeDay = visibleDays.find((day) => day.day_key === activeKey) || null;
    if (current && activeDay && current.day_key !== activeDay.day_key) {
      triggerFeedback(this, {
        hapticKey: "schedule-sticky-day",
        flashKey: "stickyDayFeedbackActive",
        flashDuration: 120
      });
    }
    this.setData({ activeStickyDay: activeDay });
  },

  async toggleFilterMenu() {
    if (this.data.multiSelectMode) return;
    if (this.data.activeKindFilter) {
      const currentFocusDayKey = (this.data.activeStickyDay && this.data.activeStickyDay.day_key)
        || (this.data.visibleDays && this.data.visibleDays[0] && this.data.visibleDays[0].day_key)
        || formatDate(new Date());
      this.setData({
        activeKindFilter: "",
        isFilterOpen: true,
        isQuickCreateOpen: false,
        visibleDays: this.buildVisibleDays(this.data.days, ""),
        activeStickyDay: null
      });
      await this.nextTickAsync();
      await this.remountTimelineView({ focusDayKey: currentFocusDayKey });
      return;
    }
    this.setData({
      isFilterOpen: !this.data.isFilterOpen,
      isQuickCreateOpen: false
    });
  },

  async selectKindFilter(event) {
    const kind = event.currentTarget.dataset.kind || "";
    const nextFilter = this.data.activeKindFilter === kind ? "" : kind;
    const currentFocusDayKey = (this.data.activeStickyDay && this.data.activeStickyDay.day_key)
      || (this.data.visibleDays && this.data.visibleDays[0] && this.data.visibleDays[0].day_key)
      || formatDate(new Date());
    this.setData({
      activeKindFilter: nextFilter,
      isFilterOpen: false,
      visibleDays: this.buildVisibleDays(this.data.days, nextFilter),
      activeStickyDay: null
    });
    await this.nextTickAsync();
    await this.remountTimelineView({ focusDayKey: currentFocusDayKey });
  },

  openCreateSchedule() {
    if (this.data.multiSelectMode) {
      this.clearMultiSelectMode();
    }
    if (this.currentTeamReadonly()) {
      this.showReadonlyTip();
      return;
    }
    const dateText = formatDate(new Date());
    this.setData(buildScheduleCreateComposerState(dateText));
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, "");
  },

  openCreateExpense() {
    this.openFinanceComposer("expense");
  },

  openCreateIncome() {
    this.openFinanceComposer("income");
  },

  openFinanceComposer(type) {
    if (this.data.multiSelectMode) {
      this.clearMultiSelectMode();
    }
    if (this.currentTeamReadonly()) {
      this.showReadonlyTip();
      return;
    }
    const now = new Date();
    const categorySuggestions = this.buildCategorySuggestions("", type);
    this.setData(buildFinanceCreateComposerState({
      type,
      now,
      categorySuggestions
    }));
    this.setData({
      compactCategorySuggestions: this.limitCompactSuggestions(categorySuggestions)
    });
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, "");
  },

  openScheduleEditor(item, dayKey = "") {
    if (this.currentTeamReadonly()) {
      this.showReadonlyTip();
      return;
    }
    this.setData(buildScheduleEditComposerState(item));
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, item.location || "");
  },

  openScheduleDuplicate(item) {
    if (this.currentTeamReadonly()) {
      this.showReadonlyTip();
      return;
    }
    this.setData(buildScheduleDuplicateComposerState(item));
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, item.location || "");
  },

  openFinanceEditor(item, dayKey = "") {
    if (this.currentTeamReadonly()) {
      this.showReadonlyTip();
      return;
    }
    const type = item.kind === "income" ? "income" : "expense";
    const category = item.category || "";
    const categorySuggestions = this.buildCategorySuggestions(category, type);
    this.setData(buildFinanceEditComposerState(
      item,
      categorySuggestions
    ));
    this.setData({
      compactCategorySuggestions: this.limitCompactSuggestions(categorySuggestions)
    });
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, item.location || "");
  },

  openFinanceDuplicate(item) {
    if (this.currentTeamReadonly()) {
      this.showReadonlyTip();
      return;
    }
    const type = item.kind === "income" ? "income" : "expense";
    const categorySuggestions = this.buildCategorySuggestions(item.category || "", type);
    this.setData(buildFinanceDuplicateComposerState(
      item,
      categorySuggestions
    ));
    this.setData({
      compactCategorySuggestions: this.limitCompactSuggestions(categorySuggestions)
    });
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, item.location || "");
  },

  closeComposer() {
    this.pendingTimelineAnchor = null;
    this.setData(buildComposerClosedState(new Date()));
  },

  toggleQuickCreate() {
    if (this.data.multiSelectMode) return;
    this.setData({
      isQuickCreateOpen: !this.data.isQuickCreateOpen,
      isFilterOpen: false
    });
  },

  onInputScheduleTitle(event) {
    this.setData({ "scheduleForm.title": event.detail.value });
  },

  onInputScheduleDescription(event) {
    this.setData({ "scheduleForm.description": event.detail.value });
  },

  onInputScheduleLocation(event) {
    const value = event.detail.value;
    this.setData({ "scheduleForm.locationText": value });
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, value);
  },

  onPickPlace(event) {
    const target = event.currentTarget.dataset.target;
    const name = event.currentTarget.dataset.name;
    if (!target || !name) return;
    if (target === "schedule") {
      this.setData({ "scheduleForm.locationText": name });
      return;
    }
    this.setData({ "financeForm.locationText": name });
  },

  onScheduleDateChange(event) {
    const date = event.detail.value;
    this.setData({
      "scheduleForm.date": date,
      "scheduleForm.end_date": date
    });
  },

  onScheduleStartTimeChange(event) {
    this.setData({ "scheduleForm.start_clock": event.detail.value });
  },

  onScheduleEndDateChange(event) {
    const endDate = event.detail.value;
    const startDate = this.data.scheduleForm.date;
    this.setData({
      "scheduleForm.end_date": !startDate || endDate >= startDate ? endDate : startDate
    });
  },

  onScheduleEndTimeChange(event) {
    this.setData({ "scheduleForm.end_clock": event.detail.value });
  },

  onToggleAllDay(event) {
    this.setData({ "scheduleForm.is_all_day": !!event.detail.value.length });
  },

  onInputAmount(event) {
    this.setData({ "financeForm.amount": event.detail.value });
  },

  onFinanceTypeChange(event) {
    const type = event.currentTarget.dataset.type;
    if (!type) return;
    const categorySuggestions = this.buildCategorySuggestions(this.data.financeForm.category, type);
    this.setData({
      "financeForm.type": type,
      categorySuggestions,
      compactCategorySuggestions: this.limitCompactSuggestions(categorySuggestions)
    });
  },

  onFinanceDateChange(event) {
    this.setData({ "financeForm.occurredDate": event.detail.value });
  },

  onFinanceTimeChange(event) {
    this.setData({ "financeForm.occurredTime": event.detail.value });
  },

  onInputCategory(event) {
    const value = event.detail.value;
    const categorySuggestions = this.buildCategorySuggestions(value, this.data.financeForm.type);
    this.setData({
      "financeForm.category": value,
      categorySuggestions,
      compactCategorySuggestions: this.limitCompactSuggestions(categorySuggestions)
    });
  },

  onPickCategory(event) {
    const category = event.currentTarget.dataset.category;
    if (!category) return;
    const categorySuggestions = this.buildCategorySuggestions(category, this.data.financeForm.type);
    this.setData({
      "financeForm.category": category,
      categorySuggestions,
      compactCategorySuggestions: this.limitCompactSuggestions(categorySuggestions)
    });
  },

  onInputFinanceLocation(event) {
    const value = event.detail.value;
    this.setData({ "financeForm.locationText": value });
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, value);
  },

  onInputFinanceNote(event) {
    this.setData({ "financeForm.note": event.detail.value });
  },

  async afterMutation(teamId, scopes, options = {}) {
    await runAfterMutation(this, teamId, scopes, options);
  },

  applySelectionState(visibleDays = [], selectedItemKeys = this.data.selectedItemKeys || []) {
    const selected = new Set(selectedItemKeys || []);
    return (visibleDays || []).map((day) => ({
      ...day,
      items: (day.items || []).map((item) => ({
        ...item,
        isSelected: selected.has(item.idKey)
      }))
    }));
  },

  clearMultiSelectMode() {
    const selectedItemKeys = [];
    this.setData({
      multiSelectMode: false,
      selectedItemKeys,
      visibleDays: this.applySelectionState(closeSwipeRows(this.data.visibleDays), selectedItemKeys)
    });
  },

  toggleMultiSelectItem(dayIndex, itemIndex) {
    const day = this.data.visibleDays[dayIndex];
    const item = day && day.items[itemIndex];
    if (!item) return;
    const selected = new Set(this.data.selectedItemKeys || []);
    if (selected.has(item.idKey)) {
      selected.delete(item.idKey);
    } else {
      selected.add(item.idKey);
    }
    const selectedItemKeys = Array.from(selected);
    this.setData({
      multiSelectMode: selectedItemKeys.length > 0,
      selectedItemKeys,
      visibleDays: this.applySelectionState(this.data.visibleDays, selectedItemKeys)
    });
  },

  enterMultiSelectMode(dayIndex, itemIndex) {
    const day = this.data.visibleDays[dayIndex];
    const item = day && day.items[itemIndex];
    if (!item) return;
    const selectedItemKeys = [item.idKey];
    this.setData({
      multiSelectMode: true,
      selectedItemKeys,
      isQuickCreateOpen: false,
      isFilterOpen: false,
      visibleDays: this.applySelectionState(closeSwipeRows(this.data.visibleDays), selectedItemKeys)
    });
  },

  resolveSelectedEntries() {
    const selected = new Set(this.data.selectedItemKeys || []);
    const familyKeys = new Set();
    const entries = [];
    (this.data.visibleDays || []).forEach((day) => {
      (day.items || []).forEach((item) => {
        const familyKey = `${item.kind}-${item.source_id}`;
        if (selected.has(item.idKey) && !familyKeys.has(familyKey)) {
          familyKeys.add(familyKey);
          entries.push(item);
        }
      });
    });
    return entries;
  },

  async duplicateTimelineEntry(teamId, item) {
    if (item.kind === "schedule") {
      return scheduleApi.createSchedule(teamId, buildSchedulePayload({
        title: item.title || "",
        description: item.description || "",
        locationText: item.location || "",
        is_all_day: !!item.is_all_day,
        date: (item.start_time || item.occur_at || "").slice(0, 10),
        start_clock: (item.start_time || item.occur_at || "").slice(11, 16) || "09:00",
        end_date: (item.end_time || item.start_time || item.occur_at || "").slice(0, 10),
        end_clock: (item.end_time || item.start_time || item.occur_at || "").slice(11, 16) || "10:00"
      }));
    }

    return scheduleApi.createFinance(teamId, buildFinancePayload({
      amount: item.amount ? `${item.amount}` : "",
      type: item.kind === "income" ? "income" : "expense",
      occurredDate: (item.occur_at || "").slice(0, 10),
      occurredTime: (item.occur_at || "").slice(11, 16) || "09:00",
      category: item.category || "",
      locationText: item.location || "",
      note: item.note || ""
    }));
  },

  async deleteTimelineEntry(item) {
    if (item.kind === "schedule") {
      return scheduleApi.deleteSchedule(item.source_id);
    }
    return scheduleApi.deleteFinance(item.source_id);
  },

  clearPendingCardTap() {
    if (this._pendingCardTapTimer) {
      clearTimeout(this._pendingCardTapTimer);
      this._pendingCardTapTimer = null;
    }
  },

  removeDeletedItemLocally(editingId, composerKind) {
    removeDeletedItemLocally(this, editingId, composerKind);
  },

  async submitComposer() {
    if (this.currentTeamReadonly()) {
      this.showReadonlyTip();
      return;
    }
    await submitComposer({
      team: this.currentTeam(),
      composerKind: this.data.composerKind,
      composerMode: this.data.composerMode,
      editingId: this.data.editingId,
      scheduleForm: this.data.scheduleForm,
      financeForm: this.data.financeForm,
      t: this.t.bind(this),
      api: scheduleApi,
      closeComposer: this.closeComposer.bind(this),
      afterMutation: this.afterMutation.bind(this)
    });
  },

  closeSwipeRows() {
    this.setData({ visibleDays: this.applySelectionState(closeSwipeRows(this.data.visibleDays)) });
  },

  openEditorByIndex(dayIndex, itemIndex) {
    const day = this.data.visibleDays[dayIndex];
    const item = day && day.items[itemIndex];
    if (!item) return;
    if (item.kind === "schedule") {
      this.openScheduleEditor(item, day.day_key);
    } else {
      this.openFinanceEditor(item, day.day_key);
    }
  },

  duplicateByIndex(dayIndex, itemIndex) {
    const day = this.data.visibleDays[dayIndex];
    const item = day && day.items[itemIndex];
    if (!item) return;
    if (item.kind === "schedule") {
      this.openScheduleDuplicate(item);
    } else {
      this.openFinanceDuplicate(item);
    }
  },

  onSwipeStart(event) {
    this.setData({
      swipeStartX: event.changedTouches[0].clientX,
      swipeStartY: event.changedTouches[0].clientY,
      swipeDirection: ""
    });
  },

  onSwipeMove(event) {
    if (this.data.multiSelectMode) return;
    const dayIndex = Number(event.currentTarget.dataset.dayIndex);
    const itemIndex = Number(event.currentTarget.dataset.itemIndex);
    if (Number.isNaN(dayIndex) || Number.isNaN(itemIndex)) return;

    const currentX = event.changedTouches[0].clientX;
    const currentY = event.changedTouches[0].clientY;
    const deltaX = currentX - this.data.swipeStartX;
    const deltaY = currentY - this.data.swipeStartY;

    let direction = this.data.swipeDirection;
    if (!direction) {
      if (Math.abs(deltaX) < DIRECTION_LOCK_THRESHOLD && Math.abs(deltaY) < DIRECTION_LOCK_THRESHOLD) {
        return;
      }
      direction = Math.abs(deltaY) >= Math.abs(deltaX) ? "vertical" : "horizontal";
      this.setData({ swipeDirection: direction });
    }
    if (direction !== "horizontal") return;

    const visibleDays = buildSwipeMoveState({
      visibleDays: this.data.visibleDays,
      dayIndex,
      itemIndex,
      deltaX,
      laziness: SWIPE_LAZINESS,
      maxSwipe: MAX_SWIPE
    });
    const item = visibleDays[dayIndex] && visibleDays[dayIndex].items[itemIndex];
    if (item && item.swipeActionReady) {
      triggerFeedback(this, { hapticKey: `schedule-swipe-${dayIndex}-${itemIndex}` });
    }
    this.setData({ visibleDays });
  },

  onSwipeEnd(event) {
    if (this.data.multiSelectMode) return;
    const dayIndex = Number(event.currentTarget.dataset.dayIndex);
    const itemIndex = Number(event.currentTarget.dataset.itemIndex);
    if (Number.isNaN(dayIndex) || Number.isNaN(itemIndex)) return;

    const result = resolveSwipeEnd({
      visibleDays: this.data.visibleDays,
      dayIndex,
      itemIndex,
      swipeDirection: this.data.swipeDirection,
      hardActionThreshold: HARD_ACTION_THRESHOLD,
      copyButtonWidth: COPY_BUTTON_WIDTH,
      editButtonWidth: EDIT_BUTTON_WIDTH
    });
    this.setData({
      visibleDays: result.visibleDays,
      swipeDirection: ""
    });
    if (result.action === "duplicate") {
      this.duplicateByIndex(dayIndex, itemIndex);
      return;
    }
    if (result.action === "delete") {
      const day = this.data.visibleDays[dayIndex];
      const item = day && day.items[itemIndex];
      this.confirmDeleteEntry(item, day && day.day_key);
    }
  },

  onTapCopy(event) {
    const dayIndex = Number(event.currentTarget.dataset.dayIndex);
    const itemIndex = Number(event.currentTarget.dataset.itemIndex);
    if (Number.isNaN(dayIndex) || Number.isNaN(itemIndex)) return;
    this.duplicateByIndex(dayIndex, itemIndex);
    this.closeSwipeRows();
  },

  onTapDelete(event) {
    const dayIndex = Number(event.currentTarget.dataset.dayIndex);
    const itemIndex = Number(event.currentTarget.dataset.itemIndex);
    if (Number.isNaN(dayIndex) || Number.isNaN(itemIndex)) return;
    const day = this.data.visibleDays[dayIndex];
    const item = day && day.items[itemIndex];
    this.confirmDeleteEntry(item, day && day.day_key);
    this.closeSwipeRows();
  },

  async confirmDeleteEntry(item, deletedDayKey = "") {
    if (!item) return;
    const isSchedule = item.kind === "schedule";
    wx.showModal({
      title: this.t(isSchedule ? "page.deleteTitleSchedule" : "page.deleteTitleFinance"),
      content: this.t(isSchedule ? "page.deleteContentSchedule" : "page.deleteContentFinance"),
      success: async (res) => {
        if (!res.confirm) return;
        try {
          this.removeTimelineEntriesLocally([item]);
          await this.deleteTimelineEntry(item);
          await this.afterMutation((this.currentTeam() || {}).id, [isSchedule ? "schedule" : "finance"]);
          wx.showToast({ title: this.t("common.delete"), icon: "success" });
        } catch (err) {
          await this.afterMutation((this.currentTeam() || {}).id, [isSchedule ? "schedule" : "finance"]);
          wx.showToast({ title: this.t("common.deleteFailed"), icon: "none" });
        }
      }
    });
  },

  onCardLongPress(event) {
    if (this.currentTeamReadonly()) {
      this.showReadonlyTip();
      return;
    }
    const dayIndex = Number(event.currentTarget.dataset.dayIndex);
    const itemIndex = Number(event.currentTarget.dataset.itemIndex);
    if (Number.isNaN(dayIndex) || Number.isNaN(itemIndex)) return;
    this.clearPendingCardTap();
    this._ignoreCardTapUntil = Date.now() + 260;
    this.enterMultiSelectMode(dayIndex, itemIndex);
    triggerFeedback(this, { hapticKey: "schedule-multiselect-enter" });
  },

  async toggleScheduleCompleted(dayIndex, itemIndex) {
    const day = this.data.visibleDays[dayIndex];
    const item = day && day.items[itemIndex];
    if (!item) return;
    if (item.kind !== "schedule") {
      this.openEditorByIndex(dayIndex, itemIndex);
      return;
    }
    if (this.currentTeamReadonly()) {
      this.showReadonlyTip();
      return;
    }

    const nextStatus = item.isCompleted ? "pending" : "completed";
    try {
      await scheduleApi.updateSchedule(item.source_id, {
        ...buildSchedulePayload({
          title: item.title || "",
          description: item.description || "",
          locationText: item.location || "",
          is_all_day: !!item.is_all_day,
          date: (item.start_time || item.occur_at || "").slice(0, 10),
          start_clock: (item.start_time || item.occur_at || "").slice(11, 16) || "09:00",
          end_date: (item.end_time || item.start_time || item.occur_at || "").slice(0, 10),
          end_clock: (item.end_time || item.start_time || item.occur_at || "").slice(11, 16) || "10:00"
        }),
        status: nextStatus
      });
      triggerFeedback(this, { hapticKey: "schedule-quick-complete" });
      await this.afterMutation((this.currentTeam() || {}).id, ["schedule"]);
      wx.showToast({ title: this.t("common.updateSuccess"), icon: "success" });
    } catch (err) {
      wx.showToast({ title: this.t("common.updateFailed"), icon: "none" });
    }
  },

  onCardTap(event) {
    if (this._ignoreCardTapUntil && Date.now() < this._ignoreCardTapUntil) {
      return;
    }
    const dayIndex = Number(event.currentTarget.dataset.dayIndex);
    const itemIndex = Number(event.currentTarget.dataset.itemIndex);
    if (Number.isNaN(dayIndex) || Number.isNaN(itemIndex)) return;
    const day = this.data.visibleDays[dayIndex];
    const item = day && day.items[itemIndex];
    if (!item) return;

    if (item.offsetX) {
      this.closeSwipeRows();
      return;
    }

    if (this.data.multiSelectMode) {
      this.toggleMultiSelectItem(dayIndex, itemIndex);
      return;
    }

    const tapKey = `${dayIndex}-${itemIndex}-${item.idKey}`;
    const now = Date.now();
    if (this._lastCardTapKey === tapKey && now - (this._lastCardTapAt || 0) < 300) {
      this.clearPendingCardTap();
      this._lastCardTapKey = "";
      this._lastCardTapAt = 0;
      this.toggleScheduleCompleted(dayIndex, itemIndex);
      return;
    }

    this._lastCardTapKey = tapKey;
    this._lastCardTapAt = now;
    this.clearPendingCardTap();
    this._pendingCardTapTimer = setTimeout(() => {
      this._pendingCardTapTimer = null;
      this.openEditorByIndex(dayIndex, itemIndex);
    }, 220);
  },

  async bulkDuplicateSelected() {
    const team = this.currentTeam();
    const selectedEntries = this.resolveSelectedEntries();
    if (!team || !selectedEntries.length) return;
    try {
      const createdEntries = await Promise.all(selectedEntries.map((item) => this.duplicateTimelineEntry(team.id, item)));
      this.clearMultiSelectMode();
      const latestCreated = createdEntries[createdEntries.length - 1] || null;
      const latestSource = selectedEntries[selectedEntries.length - 1] || null;
      await this.afterMutation(team.id, ["schedule", "finance"], {
        focusDayKey: latestCreated && latestSource
          ? (
            latestSource.kind === "schedule"
              ? `${latestCreated.start_time || ""}`.slice(0, 10)
              : `${latestCreated.occurred_at || ""}`.slice(0, 10)
          )
          : ""
      });
      wx.showToast({ title: this.t("common.createSuccess"), icon: "success" });
    } catch (err) {
      wx.showToast({ title: this.t("common.createFailed"), icon: "none" });
    }
  },

  bulkDeleteSelected() {
    const team = this.currentTeam();
    const selectedEntries = this.resolveSelectedEntries();
    if (!team || !selectedEntries.length) return;
    wx.showModal({
      title: this.t("common.delete"),
      content: `${selectedEntries.length}`,
      success: async (res) => {
        if (!res.confirm) return;
        try {
          this.removeTimelineEntriesLocally(selectedEntries, { clearSelection: true });
          await Promise.all(selectedEntries.map((item) => this.deleteTimelineEntry(item)));
          await this.afterMutation(team.id, ["schedule", "finance"]);
          wx.showToast({ title: this.t("common.delete"), icon: "success" });
        } catch (err) {
          await this.afterMutation(team.id, ["schedule", "finance"]);
          wx.showToast({ title: this.t("common.deleteFailed"), icon: "none" });
        }
      }
    });
  },

  async confirmDeleteEditing() {
    if (this.currentTeamReadonly()) {
      this.showReadonlyTip();
      return;
    }
    await confirmDeleteEditing({
      team: this.currentTeam(),
      composerMode: this.data.composerMode,
      composerKind: this.data.composerKind,
      editingId: this.data.editingId,
      t: this.t.bind(this),
      api: scheduleApi,
      closeComposer: this.closeComposer.bind(this),
      afterMutation: this.afterMutation.bind(this),
      onDeleteSuccess: ({ editingId, composerKind }) => {
        this.removeDeletedItemLocally(editingId, composerKind);
      }
    });
  },

  goAssistantPage() {
    wx.switchTab({ url: "/pages/assistant/index" });
  }
});
