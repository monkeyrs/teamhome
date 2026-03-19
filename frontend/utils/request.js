const app = getApp();

function normalizePath(path) {
  if (!path) return "";
  return path.startsWith("/") ? path : `/${path}`;
}

function request({ path, method = "GET", data = null, withAuth = true }) {
  const token = app.globalData.token || "";
  const headers = {
    "Content-Type": "application/json"
  };
  if (withAuth && token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${app.globalData.apiBaseUrl}${normalizePath(path)}`,
      method,
      data,
      header: headers,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
          return;
        }
        reject(new Error(`HTTP ${res.statusCode}: ${JSON.stringify(res.data)}`));
      },
      fail(err) {
        reject(err);
      }
    });
  });
}

function setToken(token) {
  app.globalData.token = token || "";
  wx.setStorageSync("token", app.globalData.token);
}

function setCurrentTeamId(teamId) {
  app.globalData.currentTeamId = teamId || "";
  wx.setStorageSync("currentTeamId", app.globalData.currentTeamId);
}

module.exports = {
  request,
  setToken,
  setCurrentTeamId
};
