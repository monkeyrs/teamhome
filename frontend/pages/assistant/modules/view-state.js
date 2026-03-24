function createInitialData() {
  return {
    teams: [],
    teamIndex: 0,
    teamName: "",
    teamPanelOpen: false,
    question: "",
    loading: false,
    answer: "",
    answerDataText: "",
    answerStatus: "",
    answerStatusLabel: "",
    answerCanUndo: false,
    assistantConversationSessionId: "",
    assistantMutationSessionId: "",
    assistantReturnedSessionId: "",
    assistantMissingSlots: [],
    firstMissingSlot: "",
    locale: "zh-CN",
    localeMenuOpen: false,
    languageOptions: [],
    i18n: {
      app: {},
      common: {},
      page: {},
      chart: {}
    }
  };
}

function translate(i18n, path, params) {
  const parts = String(path || "").split(".");
  let current = i18n;
  parts.forEach((part) => {
    current = current && current[part];
  });
  let text = typeof current === "string" ? current : path;
  const replacements = params || {};
  Object.keys(replacements).forEach((key) => {
    text = text.replace(`{${key}}`, replacements[key]);
  });
  return text;
}

function formatAnswerStatus(status, context) {
  const state = status || "";
  const t = context.t;
  const common = context.common || {};
  const mapping = {
    awaiting_confirmation: common.confirm || state,
    collecting: t("page.collecting"),
    blocked: t("page.blocked"),
    collecting_conflict_update: t("page.conflictUpdate"),
    cancelled: common.cancel || state,
    executed: ""
  };
  return mapping[state] || state || "";
}

function quickReplyText(token, context) {
  const t = context.t;
  const common = context.common || {};
  const mapping = {
    confirm: common.confirm,
    cancel: common.cancel,
    expense: t("page.expense"),
    income: t("page.income"),
    food: t("page.quickFood"),
    transport: t("page.quickTransport"),
    shopping: t("page.quickShopping"),
    reschedule: t("page.reschedule"),
    force_create: t("page.createAnyway")
  };
  return mapping[token] || "";
}

function mapAssistantResponse(data, options) {
  const payload = data || {};
  const missingSlots = payload.missing_slots || [];
  const mapped = {
    answer: payload.reply || "",
    answerStatus: payload.status || "",
    answerCanUndo: !!(payload.data && payload.data.can_undo),
    assistantReturnedSessionId: payload.session_id || "",
    assistantMissingSlots: missingSlots,
    firstMissingSlot: missingSlots[0] || "",
    answerDataText: ""
  };
  mapped.answerStatusLabel = options.formatStatus(mapped.answerStatus);
  if (options.clearQuestion) {
    mapped.question = "";
  }
  return mapped;
}

module.exports = {
  createInitialData,
  translate,
  formatAnswerStatus,
  quickReplyText,
  mapAssistantResponse
};
