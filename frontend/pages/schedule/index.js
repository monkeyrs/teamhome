const { request } = require("../../utils/request");
const { bootstrapSession, getCurrentTeamState } = require("../../utils/bootstrap");

const DELETE_BUTTON_WIDTH = 88;
const HARD_DELETE_THRESHOLD = 160;
const MAX_SWIPE = 220;

function pad(value) {
  return `${value}`.padStart(2, "0");
}

function formatDate(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function toLocalIso(datePart, timePart, allDay) {
  const finalTime = allDay ? "00:00" : (timePart || "00:00");
  return `${datePart}T${finalTime}:00+08:00`;
}

Page({
  data: {
    loading: false,
    teams: [],
    teamIndex: 0,
    schedules: [],
    hasTeam: true,
    teamReady: false,
    currentTeamId: "",
    form: {
      title: "",
      description: "",
      placeName: "",
      placeLatitude: null,
      placeLongitude: null,
      is_all_day: false,
      date: "",
      start_clock: "09:00",
      end_date: "",
      end_clock: "10:00"
    },
    swipeStartX: 0
  },

  async onShow() {
    const { teamId } = getCurrentTeamState();
    if (!this.data.teamReady || this.data.currentTeamId !== teamId) {
      await this.initPage();
    }
  },

  async initPage() {
    this.setData({ loading: true });
    try {
      const { teamId, teams } = await bootstrapSession();
      const now = new Date();
      this.setData({
        teams,
        hasTeam: !!teamId,
        teamReady: true,
        currentTeamId: teamId,
        "form.date": formatDate(now),
        "form.end_date": formatDate(now)
      });
      if (!teamId) {
        this.setData({ schedules: [] });
        return;
      }
      const teamIndex = Math.max(0, teams.findIndex((item) => item.id === teamId));
      this.setData({ teamIndex });
      await this.loadSchedules(teamId);
    } catch (err) {
      wx.showToast({ title: "初始化失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  currentTeam() {
    return this.data.teams[this.data.teamIndex] || null;
  },

  async loadSchedules(teamId) {
    const data = await request({ path: `/schedules?team_id=${teamId}` });
    this.setData({
      schedules: (data || []).map((item) => this.normalizeSchedule(item))
    });
  },

  normalizeSchedule(item) {
    const creatorName = item.creator_nickname || "团队成员";
    return {
      ...item,
      creatorName,
      startText: this.formatDisplayTime(item.start_time, item.is_all_day),
      endText: item.end_time ? this.formatDisplayTime(item.end_time, item.is_all_day) : "未设置",
      statusText: item.status === "completed" ? "已完成" : item.status === "cancelled" ? "已取消" : "待处理",
      locationText: item.location || "未设置地点",
      offsetX: 0,
      deleteWidth: 0
    };
  },

  formatDisplayTime(value, isAllDay) {
    if (!value) return "未设置";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    const dateText = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
    return isAllDay ? `${dateText} 全天` : `${dateText} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
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
        wx.showToast({ title: "地图选点失败", icon: "none" });
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

  async createSchedule() {
    const team = this.currentTeam();
    const form = this.data.form;
    if (!team || !form.title || !form.date) {
      wx.showToast({ title: "请填写必填项", icon: "none" });
      return;
    }
    try {
      await request({
        path: "/schedules",
        method: "POST",
        data: {
          team_id: team.id,
          title: form.title,
          description: form.description || null,
          location: form.placeName || null,
          location_latitude: form.placeLatitude,
          location_longitude: form.placeLongitude,
          is_all_day: form.is_all_day,
          start_time: toLocalIso(form.date, form.start_clock, form.is_all_day),
          end_time: toLocalIso(form.end_date || form.date, form.end_clock, form.is_all_day)
        }
      });
      wx.showToast({ title: "创建成功", icon: "success" });
      this.setData({
        form: {
          title: "",
          description: "",
          placeName: "",
          placeLatitude: null,
          placeLongitude: null,
          is_all_day: false,
          date: form.date,
          start_clock: "09:00",
          end_date: form.date,
          end_clock: "10:00"
        }
      });
      await this.loadSchedules(team.id);
    } catch (err) {
      wx.showToast({ title: "创建失败", icon: "none" });
    }
  },

  onSwipeStart(event) {
    this.setData({ swipeStartX: event.changedTouches[0].clientX });
  },

  onSwipeMove(event) {
    const currentX = event.changedTouches[0].clientX;
    const deltaX = currentX - this.data.swipeStartX;
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    const schedules = this.data.schedules.slice();
    schedules.forEach((item, itemIndex) => {
      if (itemIndex !== index) {
        item.offsetX = 0;
        item.deleteWidth = 0;
      }
    });
    const offsetX = deltaX < 0 ? Math.max(deltaX, -MAX_SWIPE) : 0;
    schedules[index].offsetX = offsetX;
    schedules[index].deleteWidth = Math.min(Math.abs(offsetX), MAX_SWIPE);
    this.setData({ schedules });
  },

  async onSwipeEnd(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    const schedules = this.data.schedules.slice();
    const current = schedules[index];
    if (!current) return;
    if (Math.abs(current.offsetX) >= HARD_DELETE_THRESHOLD) {
      await this.deleteScheduleByIndex(index);
      return;
    }
    const shouldOpen = Math.abs(current.offsetX) >= DELETE_BUTTON_WIDTH / 2;
    current.offsetX = shouldOpen ? -DELETE_BUTTON_WIDTH : 0;
    current.deleteWidth = shouldOpen ? DELETE_BUTTON_WIDTH : 0;
    this.setData({ schedules });
  },

  async onTapDelete(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    await this.deleteScheduleByIndex(index);
  },

  async deleteScheduleByIndex(index) {
    const current = this.data.schedules[index];
    const team = this.currentTeam();
    if (!current || !team) return;
    try {
      await request({ path: `/schedules/${current.id}`, method: "DELETE" });
      wx.showToast({ title: "已删除，可在最近修改中恢复", icon: "none" });
      await this.loadSchedules(team.id);
    } catch (err) {
      wx.showToast({ title: "删除失败", icon: "none" });
    }
  }
});
