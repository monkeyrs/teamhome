const { bootstrapSession, getCurrentTeamState } = require("../../utils/bootstrap");
const { applyPageLocale, translateMessage } = require("../../utils/i18n");
const { getDataVersion, markDataDirty } = require("../../utils/data-sync");
const { triggerFeedback } = require("../../utils/feedback");
const scheduleApi = require("./modules/api");
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
const DAY_RAIL_STICKY_TOP = 132;

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
    commonCategories: [],
    categorySuggestions: [],
    swipeStartX: 0,
    swipeStartY: 0,
    swipeDirection: "",
    locale: "zh-CN",
    i18n: {
      app: {},
      common: {},
      page: {},
      chart: {}
    }
  },

  onLoad() {
    this.pendingDeleteDayKey = "";
    this.pendingDeleteRowHeight = 0;
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
    applyPageLocale(this, "schedule");
    this.setData({
      visibleDays: this.buildVisibleDays(this.data.days, this.data.activeKindFilter),
      categorySuggestions: this.buildCategorySuggestions(
        this.data.financeForm.category,
        this.data.financeForm.type
      ),
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
        commonCategories: [],
        categorySuggestions: []
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
      visibleDays: this.buildVisibleDays(days, this.data.activeKindFilter),
      activeStickyDay: null
    });
    wx.nextTick(() => {
      this.rebuildStickyDayAnchors();
      this.scrollToTodayAnchor();
    });
  },

  async loadCommonCategories(teamId) {
    const categories = await scheduleApi.listFinanceCategories(teamId);
    this.setData({
      commonCategories: Array.isArray(categories) ? categories : [],
      categorySuggestions: this.buildCategorySuggestions(
        this.data.financeForm.category,
        this.data.financeForm.type
      )
    });
  },

  async loadPlaceSuggestions(teamId, query) {
    if (!teamId) return;
    try {
      const places = await scheduleApi.listPlaces(teamId, query);
      this.setData({ placeSuggestions: Array.isArray(places) ? places : [] });
    } catch (err) {
      this.setData({ placeSuggestions: [] });
    }
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

  scrollToTodayAnchor() {
    if (this.data.initialScrollDone) return;
    const anchorId = this.getTodayAnchorId();
    if (!anchorId) return;
    const query = wx.createSelectorQuery();
    query.select(`#${anchorId}`).boundingClientRect();
    query.selectViewport().scrollOffset();
    query.exec((res) => {
      const rect = res && res[0];
      const viewport = res && res[1];
      if (!rect || !viewport) return;
      const top = Math.max((viewport.scrollTop || 0) + rect.top - DAY_RAIL_STICKY_TOP, 0);
      wx.pageScrollTo({ scrollTop: top, duration: 0 });
      this.setData({ initialScrollDone: true });
      this.refreshStickyDay(top);
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
      const top = Math.max((viewport.scrollTop || 0) + rect.top - DAY_RAIL_STICKY_TOP, 0);
      wx.pageScrollTo({ scrollTop: top, duration });
      this.refreshStickyDay(top);
    });
  },

  captureDeleteContext(item, dayKey = "") {
    this.pendingDeleteDayKey = dayKey || "";
    this.pendingDeleteRowHeight = 0;
    if (!item || !item.rowDomId) return;

    const query = wx.createSelectorQuery();
    query.select(`#${item.rowDomId}`).boundingClientRect();
    query.exec((res) => {
      const rect = Array.isArray(res) ? res[0] : null;
      if (!rect || !rect.height) return;
      this.pendingDeleteRowHeight = rect.height + 8;
    });
  },

  compensateScrollAfterDelete(deletedDayKey = "") {
    const visibleDays = this.data.visibleDays || [];
    const rowHeight = Number(this.pendingDeleteRowHeight || 0);
    this.pendingDeleteRowHeight = 0;

    if (rowHeight > 0) {
      const query = wx.createSelectorQuery();
      query.selectViewport().scrollOffset();
      query.exec((res) => {
        const viewport = Array.isArray(res) ? res[0] : null;
        if (!viewport) return;
        const nextTop = Math.max((viewport.scrollTop || 0) - rowHeight, 0);
        wx.pageScrollTo({ scrollTop: nextTop, duration: 0 });
        this.refreshStickyDay(nextTop);
      });
      return;
    }

    if (!visibleDays.length || !deletedDayKey) return;
    const targetDayKey = visibleDays.some((day) => day.day_key === deletedDayKey)
      ? deletedDayKey
      : this.resolveNearestTimelineDayKey(deletedDayKey, visibleDays);
    if (!targetDayKey) return;
    wx.nextTick(() => {
      this.scrollToDay(targetDayKey, { duration: 0, silent: true });
    });
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

    const targetTop = scrollTop + DAY_RAIL_STICKY_TOP + 1;
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

  toggleFilterMenu() {
    this.setData({
      isFilterOpen: !this.data.isFilterOpen,
      isQuickCreateOpen: false
    });
  },

  selectKindFilter(event) {
    const kind = event.currentTarget.dataset.kind || "";
    const nextFilter = this.data.activeKindFilter === kind ? "" : kind;
    this.setData({
      activeKindFilter: nextFilter,
      isFilterOpen: false,
      visibleDays: this.buildVisibleDays(this.data.days, nextFilter),
      activeStickyDay: null
    }, () => {
      this.rebuildStickyDayAnchors();
    });
  },

  openCreateSchedule() {
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
    if (this.currentTeamReadonly()) {
      this.showReadonlyTip();
      return;
    }
    const now = new Date();
    this.setData(buildFinanceCreateComposerState({
      type,
      now,
      categorySuggestions: this.buildCategorySuggestions("", type)
    }));
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, "");
  },

  openScheduleEditor(item, dayKey = "") {
    if (this.currentTeamReadonly()) {
      this.showReadonlyTip();
      return;
    }
    this.captureDeleteContext(item, dayKey);
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
    this.captureDeleteContext(item, dayKey);
    const type = item.kind === "income" ? "income" : "expense";
    const category = item.category || "";
    this.setData(buildFinanceEditComposerState(
      item,
      this.buildCategorySuggestions(category, type)
    ));
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, item.location || "");
  },

  openFinanceDuplicate(item) {
    if (this.currentTeamReadonly()) {
      this.showReadonlyTip();
      return;
    }
    const type = item.kind === "income" ? "income" : "expense";
    this.setData(buildFinanceDuplicateComposerState(
      item,
      this.buildCategorySuggestions(item.category || "", type)
    ));
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, item.location || "");
  },

  closeComposer() {
    this.pendingDeleteDayKey = "";
    this.pendingDeleteRowHeight = 0;
    this.setData(buildComposerClosedState(new Date()));
  },

  toggleQuickCreate() {
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

  clearScheduleLocation() {
    this.setData({ "scheduleForm.locationText": "" });
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, "");
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
    this.setData({
      "financeForm.type": type,
      categorySuggestions: this.buildCategorySuggestions(this.data.financeForm.category, type)
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
    this.setData({
      "financeForm.category": value,
      categorySuggestions: this.buildCategorySuggestions(value, this.data.financeForm.type)
    });
  },

  onPickCategory(event) {
    const category = event.currentTarget.dataset.category;
    if (!category) return;
    this.setData({
      "financeForm.category": category,
      categorySuggestions: this.buildCategorySuggestions(category, this.data.financeForm.type)
    });
  },

  onInputFinanceLocation(event) {
    const value = event.detail.value;
    this.setData({ "financeForm.locationText": value });
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, value);
  },

  clearFinanceLocation() {
    this.setData({ "financeForm.locationText": "" });
    this.loadPlaceSuggestions((this.currentTeam() || {}).id, "");
  },

  onInputFinanceNote(event) {
    this.setData({ "financeForm.note": event.detail.value });
  },

  async afterMutation(teamId, scopes) {
    markDataDirty({ teamId, scopes });
    await Promise.all([
      this.loadTimeline(teamId),
      this.loadCommonCategories(teamId),
      this.loadPlaceSuggestions(teamId, "")
    ]);
    this.setData({
      scheduleSyncVersion: getDataVersion("schedule", teamId),
      financeSyncVersion: getDataVersion("finance", teamId)
    });
  },

  removeDeletedItemLocally(editingId, composerKind, deletedDayKey = "") {
    const targetId = `${editingId || ""}`;
    if (!targetId) return;

    const nextDays = (this.data.days || [])
      .map((day) => ({
        ...day,
        items: (day.items || []).filter((item) => {
          if (`${item.source_id || ""}` !== targetId) {
            return true;
          }
          if (composerKind === "schedule") {
            return item.kind !== "schedule";
          }
          return false;
        })
      }))
      .filter((day) => Array.isArray(day.items) && day.items.length);

    this.daySectionAnchors = [];
    this.setData({
      days: nextDays,
      visibleDays: this.buildVisibleDays(nextDays, this.data.activeKindFilter),
      activeStickyDay: null
    }, () => {
      this.rebuildStickyDayAnchors();
      this.compensateScrollAfterDelete(deletedDayKey);
    });
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
    this.setData({ visibleDays: closeSwipeRows(this.data.visibleDays) });
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

    this.setData({
      visibleDays: buildSwipeMoveState({
        visibleDays: this.data.visibleDays,
        dayIndex,
        itemIndex,
        deltaX,
        laziness: SWIPE_LAZINESS,
        maxSwipe: MAX_SWIPE
      })
    });
  },

  onSwipeEnd(event) {
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
    if (result.action === "edit") {
      this.openEditorByIndex(dayIndex, itemIndex);
    }
  },

  onTapCopy(event) {
    const dayIndex = Number(event.currentTarget.dataset.dayIndex);
    const itemIndex = Number(event.currentTarget.dataset.itemIndex);
    if (Number.isNaN(dayIndex) || Number.isNaN(itemIndex)) return;
    this.duplicateByIndex(dayIndex, itemIndex);
    this.closeSwipeRows();
  },

  onTapEdit(event) {
    const dayIndex = Number(event.currentTarget.dataset.dayIndex);
    const itemIndex = Number(event.currentTarget.dataset.itemIndex);
    if (Number.isNaN(dayIndex) || Number.isNaN(itemIndex)) return;
    this.openEditorByIndex(dayIndex, itemIndex);
    this.closeSwipeRows();
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
        this.removeDeletedItemLocally(editingId, composerKind, this.pendingDeleteDayKey);
      }
    });
  },

  goAssistantPage() {
    wx.switchTab({ url: "/pages/assistant/index" });
  }
});
