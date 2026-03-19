const { request, setToken, setCurrentUser, clearToken, setCurrentTeamId } = require("./request");

async function loginIfNeeded(forceRefresh = false) {
  const app = getApp();
  if (!forceRefresh && app.globalData.token && app.globalData.user) return app.globalData.token;

  const code = await new Promise((resolve, reject) => {
    wx.login({
      success(res) {
        if (res.code) {
          resolve(res.code);
          return;
        }
        reject(new Error("wx.login did not return code"));
      },
      fail(err) {
        reject(err);
      }
    });
  });

  const loginRes = await request({
    path: "/auth/login",
    method: "POST",
    withAuth: false,
    data: {
      code,
      nickname: "wx-user"
    }
  });
  setToken(loginRes.token || "");
  setCurrentUser(loginRes.user || null);
  return loginRes.token || "";
}

async function ensureTeam() {
  const app = getApp();
  let teams;
  try {
    teams = await request({ path: "/teams", method: "GET" });
  } catch (err) {
    if (err && err.statusCode === 401) {
      clearToken();
      await loginIfNeeded(true);
      teams = await request({ path: "/teams", method: "GET" });
    } else {
      throw err;
    }
  }
  app.globalData.teams = teams || [];
  if (app.globalData.teams.length === 0) {
    setCurrentTeamId("");
    return { teamId: "", teams: [] };
  }

  const validCurrent = app.globalData.teams.find((item) => item.id === app.globalData.currentTeamId);
  const teamId = validCurrent ? validCurrent.id : app.globalData.teams[0].id;
  setCurrentTeamId(teamId);
  return {
    teamId,
    teams: app.globalData.teams,
    user: app.globalData.user || null
  };
}

async function bootstrapSession() {
  await loginIfNeeded();
  return ensureTeam();
}

function getCurrentTeamState() {
  const app = getApp();
  return {
    teamId: app.globalData.currentTeamId || "",
    teams: app.globalData.teams || [],
    user: app.globalData.user || null
  };
}

module.exports = {
  bootstrapSession,
  getCurrentTeamState
};
