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
        const error = new Error(`HTTP ${res.statusCode}: ${JSON.stringify(res.data)}`);
        error.statusCode = res.statusCode;
        error.responseData = res.data;
        reject(error);
      },
      fail(err) {
        reject(err);
      }
    });
  });
}

function uploadFile({ path, filePath, name = "file", formData = {}, withAuth = true }) {
  const token = app.globalData.token || "";
  const headers = {};
  if (withAuth && token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: `${app.globalData.apiBaseUrl}${normalizePath(path)}`,
      filePath,
      name,
      formData,
      header: headers,
      success(res) {
        const data = res.data ? JSON.parse(res.data) : {};
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(data);
          return;
        }
        const error = new Error(`HTTP ${res.statusCode}: ${JSON.stringify(data)}`);
        error.statusCode = res.statusCode;
        error.responseData = data;
        reject(error);
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

function setCurrentUser(user) {
  app.globalData.user = user || null;
  wx.setStorageSync("user", app.globalData.user || "");
  const userId = app.globalData.user && app.globalData.user.id;
  app.globalData.currentTeamId = userId ? (wx.getStorageSync(`currentTeamId:${userId}`) || "") : "";
}

function clearToken() {
  app.globalData.token = "";
  app.globalData.user = null;
  app.globalData.currentTeamId = "";
  wx.removeStorageSync("token");
  wx.removeStorageSync("user");
}

function setCurrentTeamId(teamId) {
  app.globalData.currentTeamId = teamId || "";
  const userId = app.globalData.user && app.globalData.user.id;
  if (userId) {
    wx.setStorageSync(`currentTeamId:${userId}`, app.globalData.currentTeamId);
  }
}

module.exports = {
  request,
  uploadFile,
  setToken,
  setCurrentUser,
  clearToken,
  setCurrentTeamId
};
