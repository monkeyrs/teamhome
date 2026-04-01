const GRAPH_STAGE_ORDER = [
  "prepare",
  "loop_guard",
  "schedule_subgraph",
  "expense_subgraph",
  "collect_result",
  "commit_batch"
];

const GRAPH_NODE_DEFINITIONS = [
  {
    key: "prepare",
    titleKey: "graphPrepare",
    descKey: "graphPrepareDesc",
    tone: "primary",
    idlePhase: "1"
  },
  {
    key: "loop_guard",
    titleKey: "graphQueue",
    descKey: "graphQueueDesc",
    tone: "blue",
    idlePhase: "2"
  },
  {
    key: "schedule_subgraph",
    titleKey: "graphSchedule",
    descKey: "graphScheduleDesc",
    tone: "green",
    idlePhase: "3"
  },
  {
    key: "expense_subgraph",
    titleKey: "graphExpense",
    descKey: "graphExpenseDesc",
    tone: "orange",
    idlePhase: "4"
  },
  {
    key: "collect_result",
    titleKey: "graphCollect",
    descKey: "graphCollectDesc",
    tone: "violet",
    idlePhase: "5"
  },
  {
    key: "commit_batch",
    titleKey: "graphCommit",
    descKey: "graphCommitDesc",
    tone: "dark",
    idlePhase: "6"
  }
];

function createEmptyAssistantGraphState() {
  return {
    available: false,
    threadId: "",
    threadStatus: "",
    highlightedStages: [],
    nextNodes: [],
    updatedAt: ""
  };
}

function normalizeGraphState(input) {
  const source = input && typeof input === "object" ? input : {};
  const rawHighlightedStages = Array.isArray(source.highlighted_stages)
    ? source.highlighted_stages
    : (Array.isArray(source.highlightedStages) ? source.highlightedStages : []);
  const highlightedStages = rawHighlightedStages
    .filter((item) => GRAPH_STAGE_ORDER.includes(item))
    .filter((item, index, items) => items.indexOf(item) === index);
  const rawNextNodes = Array.isArray(source.next_nodes)
    ? source.next_nodes
    : (Array.isArray(source.nextNodes) ? source.nextNodes : []);
  return {
    available: !!source.available,
    threadId: source.thread_id || source.threadId || "",
    threadStatus: source.thread_status || source.threadStatus || "",
    highlightedStages,
    nextNodes: rawNextNodes.filter(Boolean),
    updatedAt: source.updated_at || source.updatedAt || ""
  };
}

function buildAssistantGraphNodes(graphState, graphI18n) {
  const currentGraphState = normalizeGraphState(graphState);
  const highlighted = new Set(currentGraphState.highlightedStages);
  return GRAPH_NODE_DEFINITIONS.map((item) => ({
    key: item.key,
    title: graphI18n[item.titleKey] || item.key,
    desc: graphI18n[item.descKey] || "",
    className: highlighted.has(item.key)
      ? `graph-node graph-node-${item.tone}`
      : `graph-node graph-node-muted graph-node-idle graph-node-idle-${item.tone} graph-node-idle-phase-${item.idlePhase}`
  }));
}

function createInitialData() {
  return {
    canUseNicknameInput: false,
    nicknamePromptOpen: false,
    profileNickname: "",
    profileLocked: false,
    savingProfile: false,
    teamActionLoading: false,
    teamDialogOpen: false,
    teamDialogMode: "",
    teamDialogName: "",
    teamDialogPassword: "",
    teamDialogPasswordCells: ["", "", "", ""],
    teamDialogPasswordFocus: false,
    teamDialogSubmitting: false,
    teams: [],
    realTeams: [],
    demoTeams: [],
    teamIndex: 0,
    teamName: "",
    teamPanelOpen: false,
    teamInputFocused: false,
    demoEntryOptions: [],
    question: "",
    loading: false,
    answer: "",
    processingDots: 0,
    answerDataText: "",
    answerStatus: "",
    answerStatusLabel: "",
    answerCanUndo: false,
    assistantConversationSessionId: "",
    assistantMutationSessionId: "",
    assistantReturnedSessionId: "",
    assistantMissingSlots: [],
    firstMissingSlot: "",
    assistantGraphState: createEmptyAssistantGraphState(),
    assistantGraphNodes: buildAssistantGraphNodes(createEmptyAssistantGraphState(), {}),
    assistantGraphPulseActive: false,
    locale: "zh-CN",
    localeMenuOpen: false,
    languageOptions: [],
    graphI18n: {},
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
    assistantGraphState: normalizeGraphState(payload.data && payload.data.graph_state),
    answerDataText: ""
  };
  mapped.answerStatusLabel = options.formatStatus(mapped.answerStatus);
  if (options.clearQuestion) {
    mapped.question = "";
  }
  return mapped;
}

module.exports = {
  buildAssistantGraphNodes,
  createEmptyAssistantGraphState,
  createInitialData,
  normalizeGraphState,
  translate,
  formatAnswerStatus,
  quickReplyText,
  mapAssistantResponse
};
