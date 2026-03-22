const { request } = require("../../utils/request");

Page({
  data: {
    loading: false,
    error: "",
    engine: "",
    langgraphEnabled: false,
    langgraphAvailable: false,
    langsmith: {
      tracing: false,
      endpoint: "",
      project: "",
      workspace_id: "",
      api_key_configured: false
    },
    nodes: [],
    edges: [],
    mermaid: ""
  },

  onShow() {
    this.loadGraph();
  },

  async loadGraph() {
    this.setData({ loading: true, error: "" });
    try {
      const data = await request({ path: "/assistant/orchestration", method: "GET" });
      this.setData({
        engine: data.engine || "",
        langgraphEnabled: !!data.langgraph_enabled,
        langgraphAvailable: !!data.langgraph_available,
        langsmith: data.langsmith || this.data.langsmith,
        nodes: Array.isArray(data.nodes) ? data.nodes : [],
        edges: Array.isArray(data.edges) ? data.edges : [],
        mermaid: data.mermaid || ""
      });
    } catch (err) {
      this.setData({ error: "加载编排信息失败" });
    } finally {
      this.setData({ loading: false });
    }
  },

  copyMermaid() {
    if (!this.data.mermaid) return;
    wx.setClipboardData({
      data: this.data.mermaid,
      success: () => wx.showToast({ title: "已复制 Mermaid", icon: "none" })
    });
  }
});
