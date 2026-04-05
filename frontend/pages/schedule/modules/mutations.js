const {
  buildFinancePayload,
  buildSchedulePayload
} = require("./composer");

async function submitComposer({
  team,
  composerKind,
  composerMode,
  editingId,
  scheduleForm,
  financeForm,
  t,
  api,
  closeComposer,
  afterMutation
}) {
  if (!team) return;

  if (composerKind === "schedule") {
    if (!scheduleForm.title || !scheduleForm.date) {
      wx.showToast({ title: t("common.requiredFields"), icon: "none" });
      return;
    }
    const payload = buildSchedulePayload(scheduleForm);
    try {
      let result = null;
      if (composerMode === "edit" && editingId) {
        result = await api.updateSchedule(editingId, payload);
        wx.showToast({ title: t("common.updateSuccess"), icon: "success" });
      } else {
        result = await api.createSchedule(team.id, payload);
        wx.showToast({ title: t("common.createSuccess"), icon: "success" });
      }
      closeComposer();
      await afterMutation(team.id, ["schedule"], {
        focusEntry: result ? {
          kind: "schedule",
          sourceId: `${result.id || ""}`,
          dayKey: `${result.start_time || ""}`.slice(0, 10)
        } : null
      });
    } catch (err) {
      wx.showToast({
        title: composerMode === "edit" ? t("common.updateFailed") : t("common.createFailed"),
        icon: "none"
      });
    }
    return;
  }

  if (!financeForm.amount || !financeForm.category || !financeForm.occurredDate || !financeForm.occurredTime) {
    wx.showToast({ title: t("common.requiredFields"), icon: "none" });
    return;
  }
  const payload = buildFinancePayload(financeForm);
  try {
    let result = null;
    if (composerMode === "edit" && editingId) {
      result = await api.updateFinance(editingId, payload);
      wx.showToast({ title: t("common.updateSuccess"), icon: "success" });
    } else {
      result = await api.createFinance(team.id, payload);
      wx.showToast({ title: t("common.createSuccess"), icon: "success" });
    }
    closeComposer();
    await afterMutation(team.id, ["finance"], {
      focusEntry: result ? {
        kind: result.type === "income" ? "income" : "expense",
        sourceId: `${result.id || ""}`,
        dayKey: `${result.occurred_at || ""}`.slice(0, 10)
      } : null
    });
  } catch (err) {
    wx.showToast({
      title: composerMode === "edit" ? t("common.updateFailed") : t("common.createFailed"),
      icon: "none"
    });
  }
}

async function confirmDeleteEditing({
  team,
  composerMode,
  composerKind,
  editingId,
  t,
  api,
  closeComposer,
  afterMutation,
  afterMutationOptions,
  onDeleteSuccess
}) {
  if (composerMode !== "edit" || !editingId || !team) return;

  const isSchedule = composerKind === "schedule";
  const { confirm } = await wx.showModal({
    title: t(isSchedule ? "page.deleteTitleSchedule" : "page.deleteTitleFinance"),
    content: t(isSchedule ? "page.deleteContentSchedule" : "page.deleteContentFinance"),
    confirmColor: "#fa5151"
  });
  if (!confirm) return;

  try {
    if (isSchedule) {
      await api.deleteSchedule(editingId);
    } else {
      await api.deleteFinance(editingId);
    }
    if (typeof onDeleteSuccess === "function") {
      await onDeleteSuccess({
        editingId,
        composerKind
      });
    }
    wx.showToast({ title: t("page.deleted"), icon: "success" });
    closeComposer();
    await afterMutation(team.id, [isSchedule ? "schedule" : "finance"], afterMutationOptions || {});
  } catch (err) {
    wx.showToast({ title: t("common.deleteFailed"), icon: "none" });
  }
}

module.exports = {
  confirmDeleteEditing,
  submitComposer
};
