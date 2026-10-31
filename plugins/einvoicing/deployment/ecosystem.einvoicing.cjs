/** PM2 apps for the plugin. Not added to deploy/ecosystem.config.cjs, so a normal API deploy does not start them. */

module.exports = {
  apps: [
    {
      name: "axizpos-einvoicing-api",
      cwd: "/opt/ai-pos/plugins/einvoicing",
      script: "/opt/ai-pos/apps/api/.venv/bin/python",
      args: "-m uvicorn einvoicing.main:app --host 127.0.0.1 --port 8090",
      env: { PYTHONPATH: "/opt/ai-pos/plugins/einvoicing" },
    },
    {
      name: "axizpos-einvoicing-worker",
      cwd: "/opt/ai-pos/plugins/einvoicing",
      script: "/opt/ai-pos/apps/api/.venv/bin/python",
      args: "-m einvoicing.worker",
      env: { PYTHONPATH: "/opt/ai-pos/plugins/einvoicing" },
    },
  ],
};
