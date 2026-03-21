const { request } = require("../../utils/request");
const { bootstrapSession, getCurrentTeamState } = require("../../utils/bootstrap");
const { applyPageLocale } = require("../../utils/i18n");

const LEFT_ACTION_WIDTH = 88;
const EDIT_BUTTON_WIDTH = 88;
const HARD_ACTION_THRESHOLD = 160;
const MAX_SWIPE = 220;
const SWIPE_LAZINESS = 54;
const DIRECTION_LOCK_THRESHOLD = 12;
const FUTURE_PRELOAD_DAYS = 30;
const TOP_LOAD_THRESHOLD = 80;

function pad(value) {
  return `${value}`.padStart(2, "0");
}

function formatDate(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function formatClock(date) {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function toLocalIso(datePart, timePart, allDay) {
  const finalTime = allDay ? "00:00" : (timePart || "00:00");
  return `${datePart}T${finalTime}:00+08:00`;
}

function toWindowEndIso(date) {
  return `${formatDate(date)}T23:59:59+08:00`;
}

function buildSchedulePath(teamId, options = {}) {
  const query = [`team_id=${teamId}`];
  if (options.windowStart) {
    query.push(`window_start=${encodeURIComponent(options.windowStart)}`);
  }
  if (options.windowEnd) {
    query.push(`window_end=${encodeURIComponent(options.windowEnd)}`);
  }
  return `/schedules?${query.join("&")}`;
}

function buildEmptyForm(dateText) {
  return {
    title: "",
    description: "",
    placeName: "",
    placeLatitude: null,
    placeLongitude: null,
    is_all_day: false,
    date: dateText,
    start_clock: "09:00",
    end_date: dateText,
    end_clock: "10:00"
  };
}

Page({
  data: {
    loading: false,
    teams: [],
    teamIndex: 0,
    schedules: [],
    visibleSchedules: [],
    hasTeam: true,
    teamReady: false,
    currentTeamId: "",
    showPendingOnly: false,
    futureWindowEnd: "",
    loadingMoreFuture: false,
    hasMoreFuture: true,
    initialScrollDone: false,
    composerOpen: false,
    composerMode: "create",
    editingId: "",
    form: buildEmptyForm(formatDate(new Date())),
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

  async onShow() {
    this.applyLocale();
    const { teamId } = getCurrentTeamState();
    if (!this.data.teamReady || this.data.currentTeamId !== teamId) {
      await this.initPage();
    }
  },

  applyLocale() {
    applyPageLocale(this, "schedule");
    this.setSchedules((this.data.schedules || []).map((item) => this.normalizeSchedule(item)));
  },

  t(path, params = {}) {
    const parts = path.split(".");
    let current = this.data.i18n;
    parts.forEach((part) => {
      current = current && current[part];
    });
    let text = typeof current === "string" ? current : path;
    Object.keys(params).forEach((key) => {
      text = text.replace(`{${key}}`, params[key]);
    });
    return text;
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
        composerOpen: false,
        composerMode: "create",
        editingId: "",
        form: buildEmptyForm(today),
        futureWindowEnd: "",
        loadingMoreFuture: false,
        hasMoreFuture: true,
        initialScrollDone: false
      });
      if (!teamId) {
        this.setData({ schedules: [], visibleSchedules: [] });
        return;
      }
      const teamIndex = Math.max(0, teams.findIndex((item) => item.id === teamId));
      this.setData({ teamIndex });
      await this.loadSchedules(teamId, { resetFutureWindow: true });
    } catch (err) {
      wx.showToast({ title: this.t("common.initFailed"), icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  currentTeam() {
    return this.data.teams[this.data.teamIndex] || null;
  },

  formatDisplayTime(value, isAllDay) {
    if (!value) return this.t("common.unset");
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    const dateText = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
    return isAllDay ? `${dateText} ${this.t("page.fullDay")}` : `${dateText} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  },

  normalizeSchedule(item) {
    const status = item.status || "pending";
    const nextStatus = status === "completed" ? "pending" : "completed";
    return {
      ...item,
      creatorName: item.creator_nickname || this.t("common.teamMember"),
      startText: this.formatDisplayTime(item.start_time, item.is_all_day),
      endText: item.end_time ? this.formatDisplayTime(item.end_time, item.is_all_day) : this.t("common.unset"),
      statusText: status === "completed"
        ? this.t("page.statusCompleted")
        : status === "cancelled"
          ? this.t("page.statusCancelled")
          : this.t("page.statusPending"),
      locationText: item.location || this.t("common.unset"),
      noteText: item.description || this.t("common.noNote"),
      recordSortTime: new Date(item.start_time || item.created_at || 0).getTime() || 0,
      offsetX: 0,
      leftActionWidth: 0,
      editWidth: 0,
      leftActionText: nextStatus === "completed" ? this.t("page.markDone") : this.t("page.markPending"),
      leftActionClass: nextStatus === "completed" ? "left-action-complete" : "left-action-pending"
    };
  },

  async loadSchedules(teamId, options = {}) {
    const futureWindowEnd = options.windowEnd || toWindowEndIso(addDays(new Date(), FUTURE_PRELOAD_DAYS));
    const data = await request({ path: buildSchedulePath(teamId, { windowEnd: futureWindowEnd }) });
    const schedules = (data || [])
      .map((item) => this.normalizeSchedule(item))
      .sort((a, b) => b.recordSortTime - a.recordSortTime);
    this.setSchedules(schedules);
    this.setData({
      futureWindowEnd,
      hasMoreFuture: true
    });
    if (options.resetFutureWindow) {
      wx.nextTick(() => this.scrollToTodayAnchor());
    }
  },

  setSchedules(schedules) {
    const visibleSchedules = this.data.showPendingOnly
      ? schedules.filter((item) => item.status !== "completed")
      : schedules.slice();
    this.setData({ schedules, visibleSchedules });
  },

  getTodayAnchorId() {
    const today = formatDate(new Date());
    const exact = this.data.visibleSchedules.find((item) => (item.start_time || "").slice(0, 10) === today);
    if (exact) return `schedule-${exact.id}`;
    const boundary = this.data.visibleSchedules.find((item) => (item.start_time || "").slice(0, 10) <= today);
    return boundary ? `schedule-${boundary.id}` : "";
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
      const top = Math.max((viewport.scrollTop || 0) + rect.top - 120, 0);
      wx.pageScrollTo({ scrollTop: top, duration: 0 });
      this.setData({ initialScrollDone: true });
    });
  },

  async loadMoreFutureSchedules() {
    const team = this.currentTeam();
    if (!team || this.data.loadingMoreFuture || !this.data.hasMoreFuture) return;
    const currentEnd = this.data.futureWindowEnd ? new Date(this.data.futureWindowEnd) : addDays(new Date(), FUTURE_PRELOAD_DAYS);
    const nextEnd = addDays(currentEnd, FUTURE_PRELOAD_DAYS);
    const windowStart = this.data.futureWindowEnd;
    const windowEnd = toWindowEndIso(nextEnd);
    this.setData({ loadingMoreFuture: true });
    try {
      const data = await request({ path: buildSchedulePath(team.id, { windowStart, windowEnd }) });
      const incoming = (data || []).map((item) => this.normalizeSchedule(item));
      if (!incoming.length) {
        this.setData({ hasMoreFuture: false, loadingMoreFuture: false });
        return;
      }
      const mergedMap = new Map(this.data.schedules.map((item) => [item.id, item]));
      incoming.forEach((item) => mergedMap.set(item.id, item));
      const merged = Array.from(mergedMap.values()).sort((a, b) => b.recordSortTime - a.recordSortTime);
      this.setSchedules(merged);
      this.setData({
        futureWindowEnd: windowEnd,
        loadingMoreFuture: false,
        hasMoreFuture: true
      });
    } catch (err) {
      this.setData({ loadingMoreFuture: false });
      wx.showToast({ title: this.t("common.loadFailed"), icon: "none" });
    }
  },

  openCreateComposer() {
    const dateText = this.data.form.date || formatDate(new Date());
    this.setData({
      composerOpen: true,
      composerMode: "create",
      editingId: "",
      form: buildEmptyForm(dateText)
    });
  },

  closeComposer() {
    const dateText = this.data.form.date || formatDate(new Date());
    this.setData({
      composerOpen: false,
      composerMode: "create",
      editingId: "",
      form: buildEmptyForm(dateText)
    });
  },

  openEditComposer(item) {
    if (!item) return;
    const start = item.start_time ? new Date(item.start_time) : new Date();
    const end = item.end_time ? new Date(item.end_time) : start;
    this.setData({
      composerOpen: true,
      composerMode: "edit",
      editingId: item.id,
      form: {
        title: item.title || "",
        description: item.description || "",
        placeName: item.location || "",
        placeLatitude: item.location_latitude,
        placeLongitude: item.location_longitude,
        is_all_day: !!item.is_all_day,
        date: formatDate(start),
        start_clock: formatClock(start),
        end_date: formatDate(end),
        end_clock: formatClock(end)
      }
    });
  },

  togglePendingFilter() {
    const showPendingOnly = !this.data.showPendingOnly;
    const visibleSchedules = showPendingOnly
      ? this.data.schedules.filter((item) => item.status !== "completed")
      : this.data.schedules.slice();
    this.setData({ showPendingOnly, visibleSchedules });
  },

  goAssistantPage() {
    wx.switchTab({ url: "/pages/assistant/index" });
  },

  onInputTitle(event) {
    this.setData({ "form.title": event.detail.value });
  },

  onInputDescription(event) {
    this.setData({ "form.description": event.detail.value });
  },

  chooseLocation() {
    wx.chooseLocation({
      success: (res) => {
        this.setData({
          "form.placeName": res.name || res.address || "",
          "form.placeLatitude": typeof res.latitude === "number" ? res.latitude : null,
          "form.placeLongitude": typeof res.longitude === "number" ? res.longitude : null
        });
      },
      fail: (err) => {
        if (err && /cancel/i.test(err.errMsg || "")) return;
        wx.showToast({ title: this.t("common.mapPickFailed"), icon: "none" });
      }
    });
  },

  clearLocation() {
    this.setData({
      "form.placeName": "",
      "form.placeLatitude": null,
      "form.placeLongitude": null
    });
  },

  onDateChange(event) {
    const date = event.detail.value;
    this.setData({
      "form.date": date,
      "form.end_date": this.data.form.end_date || date
    });
  },

  onTimeChange(event) {
    this.setData({ "form.start_clock": event.detail.value });
  },

  onEndDateChange(event) {
    this.setData({ "form.end_date": event.detail.value });
  },

  onEndTimeChange(event) {
    this.setData({ "form.end_clock": event.detail.value });
  },

  onToggleAllDay(event) {
    this.setData({ "form.is_all_day": !!event.detail.value.length });
  },

  buildFormPayload() {
    const form = this.data.form;
    return {
      title: form.title,
      description: form.description || null,
      location: form.placeName || null,
      location_latitude: form.placeLatitude,
      location_longitude: form.placeLongitude,
      is_all_day: form.is_all_day,
      start_time: toLocalIso(form.date, form.start_clock, form.is_all_day),
      end_time: toLocalIso(form.end_date || form.date, form.end_clock, form.is_all_day)
    };
  },

  async submitSchedule() {
    const team = this.currentTeam();
    const form = this.data.form;
    if (!team || !form.title || !form.date) {
      wx.showToast({ title: this.t("common.requiredFields"), icon: "none" });
      return;
    }

    const payload = this.buildFormPayload();

    try {
      if (this.data.composerMode === "edit" && this.data.editingId) {
        await request({
          path: `/schedules/${this.data.editingId}`,
          method: "PUT",
          data: payload
        });
        wx.showToast({ title: this.t("common.updateSuccess"), icon: "success" });
      } else {
        await request({
          path: "/schedules",
          method: "POST",
          data: {
            ...payload,
            team_id: team.id
          }
        });
        wx.showToast({ title: this.t("common.createSuccess"), icon: "success" });
      }
      this.closeComposer();
      await this.loadSchedules(team.id);
    } catch (err) {
      wx.showToast({
        title: this.data.composerMode === "edit" ? this.t("common.updateFailed") : this.t("common.createFailed"),
        icon: "none"
      });
    }
  },

  closeSwipeRows(listKey) {
    const items = this.data[listKey].slice();
    items.forEach((item) => {
      item.offsetX = 0;
      item.leftActionWidth = 0;
      item.editWidth = 0;
    });
    this.setData({ [listKey]: items });
  },

  onPageScroll(event) {
    if ((event.scrollTop || 0) <= TOP_LOAD_THRESHOLD) {
      this.loadMoreFutureSchedules();
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
    const currentX = event.changedTouches[0].clientX;
    const currentY = event.changedTouches[0].clientY;
    const deltaX = currentX - this.data.swipeStartX;
    const deltaY = currentY - this.data.swipeStartY;
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;

    let direction = this.data.swipeDirection;
    if (!direction) {
      if (Math.abs(deltaX) < DIRECTION_LOCK_THRESHOLD && Math.abs(deltaY) < DIRECTION_LOCK_THRESHOLD) {
        return;
      }
      direction = Math.abs(deltaY) >= Math.abs(deltaX) ? "vertical" : "horizontal";
      this.setData({ swipeDirection: direction });
    }
    if (direction !== "horizontal") {
      return;
    }

    const schedules = this.data.visibleSchedules.slice();
    schedules.forEach((item, itemIndex) => {
      if (itemIndex !== index) {
        item.offsetX = 0;
        item.leftActionWidth = 0;
        item.editWidth = 0;
      }
    });

    const horizontalDistance = Math.abs(deltaX);
    if (horizontalDistance <= SWIPE_LAZINESS) {
      schedules[index].offsetX = 0;
      schedules[index].leftActionWidth = 0;
      schedules[index].editWidth = 0;
      this.setData({ visibleSchedules: schedules });
      return;
    }

    if (deltaX < 0) {
      const offsetX = Math.max(deltaX + SWIPE_LAZINESS, -MAX_SWIPE);
      schedules[index].offsetX = offsetX;
      schedules[index].leftActionWidth = Math.min(Math.abs(offsetX), MAX_SWIPE);
      schedules[index].editWidth = 0;
    } else {
      const offsetX = Math.min(deltaX - SWIPE_LAZINESS, MAX_SWIPE);
      schedules[index].offsetX = offsetX;
      schedules[index].editWidth = Math.min(offsetX, MAX_SWIPE);
      schedules[index].leftActionWidth = 0;
    }
    this.setData({ visibleSchedules: schedules });
  },

  async onSwipeEnd(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    const schedules = this.data.visibleSchedules.slice();
    const current = schedules[index];
    if (!current) return;

    if (this.data.swipeDirection !== "horizontal") {
      current.offsetX = 0;
      current.leftActionWidth = 0;
      current.editWidth = 0;
      this.setData({ visibleSchedules: schedules, swipeDirection: "" });
      return;
    }

    if (current.offsetX <= -HARD_ACTION_THRESHOLD) {
      await this.toggleStatusByIndex(index);
      this.setData({ swipeDirection: "" });
      return;
    }

    if (current.offsetX >= HARD_ACTION_THRESHOLD) {
      this.openEditComposer(current);
      this.closeSwipeRows("visibleSchedules");
      this.setData({ swipeDirection: "" });
      return;
    }

    if (current.offsetX < 0) {
      const shouldOpenLeftAction = Math.abs(current.offsetX) >= LEFT_ACTION_WIDTH / 2;
      current.offsetX = shouldOpenLeftAction ? -LEFT_ACTION_WIDTH : 0;
      current.leftActionWidth = shouldOpenLeftAction ? LEFT_ACTION_WIDTH : 0;
      current.editWidth = 0;
    } else {
      const shouldOpenEdit = current.offsetX >= EDIT_BUTTON_WIDTH / 2;
      current.offsetX = shouldOpenEdit ? EDIT_BUTTON_WIDTH : 0;
      current.editWidth = shouldOpenEdit ? EDIT_BUTTON_WIDTH : 0;
      current.leftActionWidth = 0;
    }

    this.setData({ visibleSchedules: schedules, swipeDirection: "" });
  },

  async onTapLeftAction(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    await this.toggleStatusByIndex(index);
  },

  onTapEdit(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    const current = this.data.visibleSchedules[index];
    this.openEditComposer(current);
    this.closeSwipeRows("visibleSchedules");
  },

  async toggleStatusByIndex(index) {
    const current = this.data.visibleSchedules[index];
    const team = this.currentTeam();
    if (!current || !team) return;
    const nextStatus = current.status === "completed" ? "pending" : "completed";
    try {
      await request({
        path: `/schedules/${current.id}`,
        method: "PUT",
        data: {
          title: current.title,
          description: current.description || null,
          location: current.location || null,
          location_latitude: current.location_latitude,
          location_longitude: current.location_longitude,
          is_all_day: !!current.is_all_day,
          start_time: current.start_time,
          end_time: current.end_time,
          status: nextStatus
        }
      });
      await this.loadSchedules(team.id);
    } catch (err) {
      wx.showToast({ title: this.t("common.updateFailed"), icon: "none" });
    }
  },

  async confirmDeleteEditingSchedule() {
    if (this.data.composerMode !== "edit" || !this.data.editingId) return;
    const team = this.currentTeam();
    if (!team) return;
    const { confirm } = await wx.showModal({
      title: this.t("page.deleteTitle"),
      content: this.t("page.deleteContent"),
      confirmColor: "#fa5151"
    });
    if (!confirm) return;
    try {
      await request({ path: `/schedules/${this.data.editingId}`, method: "DELETE" });
      wx.showToast({ title: this.t("page.deleted"), icon: "success" });
      this.closeComposer();
      await this.loadSchedules(team.id);
    } catch (err) {
      wx.showToast({ title: this.t("common.deleteFailed"), icon: "none" });
    }
  }
});
