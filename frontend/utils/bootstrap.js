const { request, setToken, setCurrentTeamId } = require("./request");

async function loginIfNeeded() {
  const app = getApp();
  if (app.globalData.token) return app.globalData.token;

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
  getApp().globalData.user = loginRes.user || null;
  return loginRes.token || "";
}

async function ensureTeam() {
  const app = getApp();
  const teams = await request({ path: "/teams", method: "GET" });
  app.globalData.teams = teams || [];

  if (app.globalData.teams.length === 0) {
    const created = await request({
      path: "/teams",
      method: "POST",
      data: { name: "My Team" }
    });
    app.globalData.teams = [created];
  }

  const validCurrent = app.globalData.teams.find((item) => item.id === app.globalData.currentTeamId);
  const teamId = validCurrent ? validCurrent.id : app.globalData.teams[0].id;
  setCurrentTeamId(teamId);
  return {
    teamId,
    teams: app.globalData.teams
  };
}

async function bootstrapSession() {
  await loginIfNeeded();
  return ensureTeam();
}

module.exports = {
  bootstrapSession
};
