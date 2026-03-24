const { request, downloadFile } = require("../../../utils/request");

function listSchedules(teamId) {
  return request({
    path: `/schedules?team_id=${teamId}`
  });
}

function listFinance(teamId) {
  return request({
    path: `/finance?team_id=${teamId}`
  });
}

function downloadAssistantData() {
  return downloadFile({
    path: "/assistant/export-data"
  });
}

module.exports = {
  listSchedules,
  listFinance,
  downloadAssistantData
};
