const { request } = require("../../utils/request");
const { bootstrapSession, getCurrentTeamState } = require("../../utils/bootstrap");
const { applyPageLocale } = require("../../utils/i18n");

const COPY_BUTTON_WIDTH = 88;
const EDIT_BUTTON_WIDTH = 88;
const HARD_ACTION_THRESHOLD = 160;
const MAX_SWIPE = 220;
const SWIPE_LAZINESS = 54;
const DIRECTION_LOCK_THRESHOLD = 12;

function pad(value) {
  return `${value}`.padStart(2, "0");
}

function formatDate(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function formatTime(date) {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function toLocalIso(datePart, timePart) {
  return `${datePart}T${timePart || "00:00"}:00+08:00`;
}

function formatDisplayTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function buildEmptyForm(now = new Date()) {
  return {
    amount: "",
    type: "expense",
    occurredDate: formatDate(now),
    occurredTime: formatTime(now),
    category: "",
    placeName: "",
    placeLatitude: null,
    placeLongitude: null,
    note: ""
  };
}

Page({
  data: {
    loading: false,
    teams: [],
    teamIndex: 0,
    records: [],
    visibleRecords: [],
    showExpenseOnly: false,
    showIncomeOnly: false,
    commonCategories: [],
    hasTeam: true,
    teamReady: false,
    currentTeamId: "",
    composerOpen: false,
    composerMode: "create",
    editingId: "",
    form: buildEmptyForm(),
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
    applyPageLocale(this, "finance");
    this.setRecords((this.data.records || []).map((item) => this.normalizeRecord(item)));
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
      this.setData({
        teams,
        hasTeam: !!teamId,
        teamReady: true,
        currentTeamId: teamId,
        showExpenseOnly: false,
        showIncomeOnly: false,
        composerOpen: false,
        composerMode: "create",
        editingId: "",
        form: buildEmptyForm(),
        commonCategories: []
      });
      if (!teamId) {
        this.setData({ records: [], visibleRecords: [] });
        return;
      }
      const teamIndex = Math.max(0, teams.findIndex((item) => item.id === teamId));
      this.setData({ teamIndex });
      await Promise.all([this.loadFinance(teamId), this.loadCommonCategories(teamId)]);
    } catch (err) {
      wx.showToast({ title: this.t("common.initFailed"), icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  currentTeam() {
    return this.data.teams[this.data.teamIndex] || null;
  },

  normalizeRecord(item) {
    const occurredAt = item.occurred_at || item.created_at;
    return {
      ...item,
      creatorName: item.creator_nickname || this.t("common.teamMember"),
      amountText: `${item.type === "income" ? "+" : "-"}${item.amount}`,
      locationText: item.location || this.t("common.unset"),
      occurredText: formatDisplayTime(occurredAt) || this.t("common.unset"),
      recordSortTime: new Date(occurredAt || 0).getTime() || 0,
      offsetX: 0,
      leftActionWidth: 0,
      editWidth: 0
    };
  },

  async loadFinance(teamId) {
    const data = await request({ path: `/finance?team_id=${teamId}` });
    const records = (data || [])
      .map((item) => this.normalizeRecord(item))
      .sort((a, b) => b.recordSortTime - a.recordSortTime);
    this.setRecords(records);
  },

  setRecords(records) {
    let visibleRecords = records.slice();
    if (this.data.showExpenseOnly) {
      visibleRecords = visibleRecords.filter((item) => item.type === "expense");
    } else if (this.data.showIncomeOnly) {
      visibleRecords = visibleRecords.filter((item) => item.type === "income");
    }
    this.setData({ records, visibleRecords });
  },

  async loadCommonCategories(teamId) {
    const categories = await request({ path: `/finance/categories?team_id=${teamId}` });
    this.setData({ commonCategories: Array.isArray(categories) ? categories : [] });
  },

  openCreateComposer() {
    this.setData({
      composerOpen: true,
      composerMode: "create",
      editingId: "",
      form: buildEmptyForm()
    });
  },

  closeComposer() {
    this.setData({
      composerOpen: false,
      composerMode: "create",
      editingId: "",
      form: buildEmptyForm()
    });
  },

  openEditComposer(item) {
    if (!item) return;
    const occurredAt = item.occurred_at || item.created_at;
    const occurredDate = occurredAt ? new Date(occurredAt) : new Date();
    this.setData({
      composerOpen: true,
      composerMode: "edit",
      editingId: item.id,
      form: {
        amount: item.amount ? `${item.amount}` : "",
        type: item.type || "expense",
        occurredDate: formatDate(occurredDate),
        occurredTime: formatTime(occurredDate),
        category: item.category || "",
        placeName: item.location || "",
        placeLatitude: item.location_latitude,
        placeLongitude: item.location_longitude,
        note: item.note || ""
      }
    });
  },

  goAssistantPage() {
    wx.switchTab({ url: "/pages/assistant/index" });
  },

  toggleExpenseFilter() {
    const showExpenseOnly = !this.data.showExpenseOnly;
    this.setData({
      showExpenseOnly,
      showIncomeOnly: false
    });
    this.setRecords(this.data.records.slice());
  },

  toggleIncomeFilter() {
    const showIncomeOnly = !this.data.showIncomeOnly;
    this.setData({
      showExpenseOnly: false,
      showIncomeOnly
    });
    this.setRecords(this.data.records.slice());
  },

  onInputAmount(event) {
    this.setData({ "form.amount": event.detail.value });
  },

  onTypeChange(event) {
    const type = event.currentTarget.dataset.type;
    if (!type) return;
    this.setData({ "form.type": type });
  },

  onDateChange(event) {
    this.setData({ "form.occurredDate": event.detail.value });
  },

  onTimeChange(event) {
    this.setData({ "form.occurredTime": event.detail.value });
  },

  onInputCategory(event) {
    this.setData({ "form.category": event.detail.value });
  },

  onPickCategory(event) {
    const category = event.currentTarget.dataset.category;
    if (!category) return;
    this.setData({ "form.category": category });
  },

  onInputNote(event) {
    this.setData({ "form.note": event.detail.value });
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

  async submitRecord() {
    const team = this.currentTeam();
    const form = this.data.form;
    if (!team || !form.amount || !form.category || !form.occurredDate || !form.occurredTime) {
      wx.showToast({ title: this.t("common.requiredFields"), icon: "none" });
      return;
    }

    const payload = {
      amount: Number(form.amount),
      type: form.type,
      occurred_at: toLocalIso(form.occurredDate, form.occurredTime),
      category: form.category,
      location: form.placeName || null,
      location_latitude: form.placeLatitude,
      location_longitude: form.placeLongitude,
      note: form.note || null
    };

    try {
      if (this.data.composerMode === "edit" && this.data.editingId) {
        await request({
          path: `/finance/${this.data.editingId}`,
          method: "PUT",
          data: payload
        });
        wx.showToast({ title: this.t("common.updateSuccess"), icon: "success" });
      } else {
        await request({
          path: "/finance",
          method: "POST",
          data: {
            ...payload,
            team_id: team.id
          }
        });
        wx.showToast({ title: this.t("common.createSuccess"), icon: "success" });
      }
      this.closeComposer();
      await Promise.all([this.loadFinance(team.id), this.loadCommonCategories(team.id)]);
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

    const visibleRecords = this.data.visibleRecords.slice();
    visibleRecords.forEach((item, itemIndex) => {
      if (itemIndex !== index) {
        item.offsetX = 0;
        item.leftActionWidth = 0;
        item.editWidth = 0;
      }
    });

    const horizontalDistance = Math.abs(deltaX);
    if (horizontalDistance <= SWIPE_LAZINESS) {
      visibleRecords[index].offsetX = 0;
      visibleRecords[index].leftActionWidth = 0;
      visibleRecords[index].editWidth = 0;
      this.setData({ visibleRecords });
      return;
    }

    if (deltaX < 0) {
      const offsetX = Math.max(deltaX + SWIPE_LAZINESS, -MAX_SWIPE);
      visibleRecords[index].offsetX = offsetX;
      visibleRecords[index].leftActionWidth = Math.min(Math.abs(offsetX), MAX_SWIPE);
      visibleRecords[index].editWidth = 0;
    } else {
      const offsetX = Math.min(deltaX - SWIPE_LAZINESS, MAX_SWIPE);
      visibleRecords[index].offsetX = offsetX;
      visibleRecords[index].editWidth = Math.min(offsetX, MAX_SWIPE);
      visibleRecords[index].leftActionWidth = 0;
    }
    this.setData({ visibleRecords });
  },

  async onSwipeEnd(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    const visibleRecords = this.data.visibleRecords.slice();
    const current = visibleRecords[index];
    if (!current) return;

    if (this.data.swipeDirection !== "horizontal") {
      current.offsetX = 0;
      current.leftActionWidth = 0;
      current.editWidth = 0;
      this.setData({ visibleRecords, swipeDirection: "" });
      return;
    }

    if (current.offsetX <= -HARD_ACTION_THRESHOLD) {
      this.duplicateRecordByIndex(index);
      this.setData({ swipeDirection: "" });
      return;
    }

    if (current.offsetX >= HARD_ACTION_THRESHOLD) {
      this.openEditComposer(current);
      this.closeSwipeRows("visibleRecords");
      this.setData({ swipeDirection: "" });
      return;
    }

    if (current.offsetX < 0) {
      const shouldOpenCopy = Math.abs(current.offsetX) >= COPY_BUTTON_WIDTH / 2;
      current.offsetX = shouldOpenCopy ? -COPY_BUTTON_WIDTH : 0;
      current.leftActionWidth = shouldOpenCopy ? COPY_BUTTON_WIDTH : 0;
      current.editWidth = 0;
    } else {
      const shouldOpenEdit = current.offsetX >= EDIT_BUTTON_WIDTH / 2;
      current.offsetX = shouldOpenEdit ? EDIT_BUTTON_WIDTH : 0;
      current.editWidth = shouldOpenEdit ? EDIT_BUTTON_WIDTH : 0;
      current.leftActionWidth = 0;
    }

    this.setData({ visibleRecords, swipeDirection: "" });
  },

  onTapLeftAction(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    this.duplicateRecordByIndex(index);
  },

  onTapEdit(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    const current = this.data.visibleRecords[index];
    this.openEditComposer(current);
    this.closeSwipeRows("visibleRecords");
  },

  duplicateRecordByIndex(index) {
    const current = this.data.visibleRecords[index];
    if (!current) return;
    const occurredAt = current.occurred_at || current.created_at;
    const occurredDate = occurredAt ? new Date(occurredAt) : new Date();
    this.setData({
      composerOpen: true,
      composerMode: "create",
      editingId: "",
      form: {
        amount: current.amount ? `${current.amount}` : "",
        type: current.type || "expense",
        occurredDate: formatDate(occurredDate),
        occurredTime: formatTime(occurredDate),
        category: current.category || "",
        placeName: current.location || "",
        placeLatitude: current.location_latitude,
        placeLongitude: current.location_longitude,
        note: current.note || ""
      }
    });
    this.closeSwipeRows("visibleRecords");
  },

  async confirmDeleteEditingRecord() {
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
      await request({ path: `/finance/${this.data.editingId}`, method: "DELETE" });
      wx.showToast({ title: this.t("page.deleted"), icon: "success" });
      this.closeComposer();
      await Promise.all([this.loadFinance(team.id), this.loadCommonCategories(team.id)]);
    } catch (err) {
      wx.showToast({ title: this.t("common.deleteFailed"), icon: "none" });
    }
  }
});
