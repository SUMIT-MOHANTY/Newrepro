module.exports = {
  apps: [
    {
      name: "dsuite-ui-stage",
      script: "npm",
      args: "run preview -- --host 0.0.0.0 --port 5172",
      env: {
        NODE_ENV: "production"
      }
    }
  ]
};

