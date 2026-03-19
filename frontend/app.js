App({
  globalData: {
    apiBaseUrl: "http://127.0.0.1:8000",
    token: "",
    currentTeamId: "",
    teams: [],
    user: null
  },
  onLaunch() {
    const token = wx.getStorageSync("token") || "";
    const currentTeamId = wx.getStorageSync("currentTeamId") || "";
    this.globalData.token = token;
    this.globalData.currentTeamId = currentTeamId;
  }
});
