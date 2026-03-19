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
    const user = wx.getStorageSync("user") || null;
    this.globalData.token = token;
    this.globalData.user = user;
    if (user && user.id) {
      this.globalData.currentTeamId = wx.getStorageSync(`currentTeamId:${user.id}`) || "";
    }
  }
});
