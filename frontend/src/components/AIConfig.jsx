const AIConfig = ({ onConfigChange, config }) => {
    // Fallback to empty default object to prevent crashes and ensure rendering
    const safeConfig = config || { apiUrl: '', apiKey: '', model: '' };

    const handleChange = (e) => {
        const { name, value } = e.target;
        if (onConfigChange) {
            onConfigChange({ ...safeConfig, [name]: value });
        }
    };

    return (
        <div className="bg-app-bg-page p-4 rounded-lg border border-app-border mt-4 mb-4">
            <h3 className="text-md font-semibold mb-3 text-app-text-label">AI Analysis Configuration (Optional Override)</h3>
            <div className="grid grid-cols-1 gap-4">
                <div>
                    <label className="block text-sm font-medium text-app-text-label mb-1">API URL</label>
                    <input
                        type="text"
                        name="apiUrl"
                        value={safeConfig.apiUrl || ''}
                        onChange={handleChange}
                        placeholder="Your base Url"
                        className="w-full p-2 border border-app-border rounded text-sm focus:ring-app-primary focus:border-app-primary"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-app-text-label mb-1">API Key</label>
                    <input
                        type="password"
                        name="apiKey"
                        value={safeConfig.apiKey || ''}
                        onChange={handleChange}
                        placeholder="sk-..."
                        className="w-full p-2 border border-app-border rounded text-sm focus:ring-app-primary focus:border-app-primary"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-app-text-label mb-1">Model Name</label>
                    <input
                        type="text"
                        name="model"
                        value={safeConfig.model || ''}
                        onChange={handleChange}
                        placeholder="GPT-4"
                        className="w-full p-2 border border-app-border rounded text-sm focus:ring-app-primary focus:border-app-primary"
                    />
                </div>
            </div>
            <p className="text-xs text-app-text-muted mt-2">
                Leave blank to use default server configuration. Entering values here will override defaults for this analysis.
            </p>
        </div>
    );
};

export default AIConfig;
