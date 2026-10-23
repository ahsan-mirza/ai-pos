/** PM2 processes on the VM. Logs: `pm2 logs`, `pm2 logs ai-pos-api`, `pm2 logs ai-pos-admin`, `pm2 logs ai-pos-console`. */
module.exports = {
  apps: [
    {
      name: "ai-pos-api",
      cwd: "/opt/ai-pos/apps/api",
      script: "/opt/ai-pos/apps/api/.venv/bin/python",
      args: "-m app.serve",
      interpreter: "none",
      env: {
        APP_ENV: "production",
        PYTHONUNBUFFERED: "1",
      },
    },
    {
      name: "ai-pos-admin",
      cwd: "/home/ubuntu/ai-pos-deploy",
      script: "/home/ubuntu/ai-pos-deploy/serve-admin.mjs",
      interpreter: "node",
      env: {
        ADMIN_ROOT: "/var/www/ai-pos-admin",
        HOST: "127.0.0.1",
        PORT: "4173",
      },
    },
    {
      name: "ai-pos-console",
      cwd: "/home/ubuntu/ai-pos-deploy",
      script: "/home/ubuntu/ai-pos-deploy/serve-admin.mjs",
      interpreter: "node",
      env: {
        ADMIN_ROOT: "/var/www/ai-pos-console",
        HOST: "127.0.0.1",
        PORT: "4174",
      },
    },
  ],
};
