const { request, setToken, setCurrentUser, clearToken, setCurrentTeamId } = require("./request");
const { getLocale } = require("./i18n");

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

  const locale = getLocale();
  const loginRes = await request({
    path: "/auth/login",
    method: "POST",
    withAuth: false,
    data: {
      code,
      language: locale
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
  const realTeams = app.globalData.teams.filter((item) => !item.is_demo);
  const demoTeams = app.globalData.teams.filter((item) => !!item.is_demo);
  if (app.globalData.teams.length === 0) {
    setCurrentTeamId("");
    return {
      teamId: "",
      teams: [],
      realTeams,
      demoTeams,
      currentEntry: null,
      user: app.globalData.user || null,
      capabilities: {
        hasRealTeams: false,
        hasDemoTeams: false,
        shouldPromptTeamEntry: true
      }
    };
  }

  const validCurrent = app.globalData.teams.find((item) => item.id === app.globalData.currentTeamId);
  const preferredTeam = validCurrent || realTeams[0] || demoTeams[0] || app.globalData.teams[0];
  const teamId = preferredTeam ? preferredTeam.id : "";
  setCurrentTeamId(teamId);
  return {
    teamId,
    teams: app.globalData.teams,
    realTeams,
    demoTeams,
    currentEntry: preferredTeam || null,
    capabilities: {
      hasRealTeams: realTeams.length > 0,
      hasDemoTeams: demoTeams.length > 0,
      shouldPromptTeamEntry: realTeams.length === 0
    },
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
