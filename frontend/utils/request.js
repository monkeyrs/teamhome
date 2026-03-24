const app = getApp();
const { setLocale } = require("./i18n");

function normalizePath(path) {
  if (!path) return "";
  return path.startsWith("/") ? path : `/${path}`;
}

function stripUtf8Bom(text) {
  if (typeof text !== "string" || text.length === 0) return text;
  return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

function parseMaybeJson(data) {
  if (typeof data !== "string") return data;
  const cleaned = stripUtf8Bom(data).trim();
  if (!cleaned) return {};
  try {
    return JSON.parse(cleaned);
  } catch (err) {
    return cleaned;
  }
}

function buildRequestBody(method, data) {
  if (data == null) return data;
  const upperMethod = String(method || "GET").toUpperCase();
  if (upperMethod === "GET" || upperMethod === "DELETE") return data;
  if (typeof data === "string") return stripUtf8Bom(data);
  return JSON.stringify(data);
}

function request({ path, method = "GET", data = null, withAuth = true }) {
  const token = app.globalData.token || "";
  const headers = {
    "Content-Type": "application/json; charset=UTF-8",
    Accept: "application/json"
  };
  if (withAuth && token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${app.globalData.apiBaseUrl}${normalizePath(path)}`,
      method,
      data: buildRequestBody(method, data),
      header: headers,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(parseMaybeJson(res.data));
          return;
        }
        const responseData = parseMaybeJson(res.data);
        const error = new Error(`HTTP ${res.statusCode}: ${JSON.stringify(responseData)}`);
        error.statusCode = res.statusCode;
        error.responseData = responseData;
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
        const data = parseMaybeJson(res.data || "{}");
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

function downloadFile({ path, withAuth = true }) {
  const token = app.globalData.token || "";
  const headers = {};
  if (withAuth && token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url: `${app.globalData.apiBaseUrl}${normalizePath(path)}`,
      header: headers,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res);
          return;
        }
        const error = new Error(`HTTP ${res.statusCode}`);
        error.statusCode = res.statusCode;
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
  if (app.globalData.user && app.globalData.user.language) {
    setLocale(app.globalData.user.language);
  }
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
  downloadFile,
  setToken,
  setCurrentUser,
  clearToken,
  setCurrentTeamId
};
