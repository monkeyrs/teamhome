const { request } = require("../../../utils/request");

function listTimeline(teamId, { windowStart, windowEnd }) {
  return request({
    path: `/timeline?team_id=${teamId}&window_start=${encodeURIComponent(windowStart)}&window_end=${encodeURIComponent(windowEnd)}`
  });
}

function listFinanceCategories(teamId) {
  return request({ path: `/finance/categories?team_id=${teamId}` });
}

function listPlaces(teamId, query = "") {
  const trimmed = String(query || "").trim();
  const path = trimmed
    ? `/places?team_id=${teamId}&q=${encodeURIComponent(trimmed)}`
    : `/places?team_id=${teamId}`;
  return request({ path });
}

function createSchedule(teamId, payload) {
  return request({
    path: "/schedules",
    method: "POST",
    data: {
      ...payload,
      team_id: teamId
    }
  });
}

function updateSchedule(scheduleId, payload) {
  return request({
    path: `/schedules/${scheduleId}`,
    method: "PUT",
    data: payload
  });
}

function deleteSchedule(scheduleId) {
  return request({
    path: `/schedules/${scheduleId}`,
    method: "DELETE"
  });
}

function createFinance(teamId, payload) {
  return request({
    path: "/finance",
    method: "POST",
    data: {
      ...payload,
      team_id: teamId
    }
  });
}

function updateFinance(recordId, payload) {
  return request({
    path: `/finance/${recordId}`,
    method: "PUT",
    data: payload
  });
}

function deleteFinance(recordId) {
  return request({
    path: `/finance/${recordId}`,
    method: "DELETE"
  });
}

module.exports = {
  listTimeline,
  listFinanceCategories,
  listPlaces,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  createFinance,
  updateFinance,
  deleteFinance
};
