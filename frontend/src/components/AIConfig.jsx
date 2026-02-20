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
        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200 mt-4 mb-4">
            <h3 className="text-md font-semibold mb-3 text-gray-700">AI Analysis Configuration (Optional Override)</h3>
            <div className="grid grid-cols-1 gap-4">
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">API URL</label>
                    <input
                        type="text"
                        name="apiUrl"
                        value={safeConfig.apiUrl || ''}
                        onChange={handleChange}
                        placeholder="Your base Url"
                        className="w-full p-2 border border-gray-300 rounded text-sm focus:ring-blue-500 focus:border-blue-500"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
                    <input
                        type="password"
                        name="apiKey"
                        value={safeConfig.apiKey || ''}
                        onChange={handleChange}
                        placeholder="sk-..."
                        className="w-full p-2 border border-gray-300 rounded text-sm focus:ring-blue-500 focus:border-blue-500"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Model Name</label>
                    <input
                        type="text"
                        name="model"
                        value={safeConfig.model || ''}
                        onChange={handleChange}
                        placeholder="GPT-4"
                        className="w-full p-2 border border-gray-300 rounded text-sm focus:ring-blue-500 focus:border-blue-500"
                    />
                </div>
            </div>
            <p className="text-xs text-gray-500 mt-2">
                Leave blank to use default server configuration. Entering values here will override defaults for this analysis.
            </p>
        </div>
    );
};

export default AIConfig;
