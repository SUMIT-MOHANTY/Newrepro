import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Search, FolderOpen, Check } from 'lucide-react';

export default function ProjectDropdown({ projects = [], selectedKey, onSelect, className = '', theme = 'light' }) {
    const [isOpen, setIsOpen] = useState(false);
    const [search, setSearch] = useState('');
    const dropdownRef = useRef(null);
    const searchRef = useRef(null);

    const selectedProject = projects.find(p => p.key === selectedKey) || null;

    const filtered = projects.filter(p =>
        (p.name || '').toLowerCase().includes(search.toLowerCase())
    );

    // Close on outside click
    useEffect(() => {
        const handleClickOutside = (e) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
                setIsOpen(false);
                setSearch('');
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    // Auto-focus search when opened
    useEffect(() => {
        if (isOpen && searchRef.current) {
            searchRef.current.focus();
        }
    }, [isOpen]);

    const getStatusColor = (status) => {
        switch (status) {
            case 'analysis_complete': return 'bg-emerald-500';
            case 'ready_for_upload': return 'bg-amber-400';
            case 'processing': return 'bg-blue-500';
            default: return 'bg-gray-400';
        }
    };

    const getStatusLabel = (status) => {
        switch (status) {
            case 'analysis_complete': return 'Complete';
            case 'ready_for_upload': return 'Pending';
            case 'processing': return 'In Progress';
            default: return 'Unknown';
        }
    };

    return (
        <div ref={dropdownRef} className={`relative ${className}`}>
            {/* Trigger Button */}
            <button
                type="button"
                onClick={() => setIsOpen(!isOpen)}
                className={`
                    w-full flex items-center justify-between gap-2.5
                    ${theme === 'dark'
                        ? 'bg-transparent hover:bg-white/5 rounded-md px-3 py-1.5'
                        : 'bg-app-bg-card border-2 border-app-border hover:border-app-border rounded-xl px-4 py-2.5'
                    }
                    text-sm font-semibold
                    shadow-sm
                    transition-all duration-200 ease-in-out
                    focus:outline-none focus:ring-2 focus:ring-white/30
                    ${isOpen && theme === 'dark' ? 'bg-white/10' : ''}
                    ${isOpen && theme !== 'dark' ? 'border-blue-400 ring-4 ring-blue-100 shadow-md' : ''}
                `}
            >
                <div className="flex items-center gap-2 min-w-0">
                    <div className={`w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 shadow-sm ${theme === 'dark' ? 'bg-white/10' : 'bg-gradient-to-br from-blue-500 to-indigo-600'}`}>
                        <FolderOpen className={`w-3 h-3 ${theme === 'dark' ? 'text-white' : 'text-white'}`} />
                    </div>
                    <div className="text-left min-w-0">
                        <p className={`text-[10px] font-medium leading-none mb-0.5 ${theme === 'dark' ? 'text-white/70' : 'text-app-text-light'}`}>Project</p>
                        <p className={`text-xs font-bold truncate leading-tight ${theme === 'dark' ? 'text-white' : 'text-gray-800'}`}>
                            {selectedProject?.name || 'Select a project'}
                        </p>
                    </div>
                </div>
                <ChevronDown className={`w-3.5 h-3.5 flex-shrink-0 transition-transform duration-200 ${theme === 'dark' ? 'text-white/70' : 'text-app-text-light'} ${isOpen ? 'rotate-180' : ''}`} />
            </button>

            {/* Dropdown Panel */}
            {isOpen && (
                <div className="absolute top-full left-0 right-0 mt-2 z-50
                    bg-app-bg-card rounded-xl border border-app-border shadow-xl
                    overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150"
                    style={{ maxHeight: '340px' }}
                >
                    {/* Search */}
                    {projects.length > 3 && (
                        <div className="p-2.5 border-b border-app-border-light">
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-app-text-light" />
                                <input
                                    ref={searchRef}
                                    type="text"
                                    value={search}
                                    onChange={(e) => setSearch(e.target.value)}
                                    placeholder="Search projects..."
                                    className="w-full pl-9 pr-3 py-2 text-sm bg-app-bg-page border border-app-border rounded-lg
                                        focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-300 focus:bg-app-bg-card
                                        placeholder:text-app-text-light text-gray-800 font-medium transition-all"
                                />
                            </div>
                        </div>
                    )}

                    {/* Options List */}
                    <div className="overflow-y-auto" style={{ maxHeight: '270px' }}>
                        {filtered.length === 0 ? (
                            <div className="p-6 text-center text-sm text-app-text-light font-medium">
                                No projects found
                            </div>
                        ) : (
                            filtered.map((project) => {
                                const isSelected = project.key === selectedKey;
                                return (
                                    <button
                                        key={project.key}
                                        type="button"
                                        onClick={() => {
                                            onSelect(project);
                                            setIsOpen(false);
                                            setSearch('');
                                        }}
                                        className={`
                                            w-full flex items-center gap-3 px-4 py-3 text-left
                                            transition-colors duration-100
                                            ${isSelected
                                                ? 'bg-app-primary-light border-l-3 border-l-blue-500'
                                                : 'hover:bg-app-bg-page border-l-3 border-l-transparent'
                                            }
                                        `}
                                    >
                                        <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 shadow-sm ${isSelected
                                            ? 'bg-gradient-to-br from-blue-500 to-indigo-600'
                                            : 'bg-gradient-to-br from-gray-200 to-gray-300'
                                            }`}>
                                            {isSelected
                                                ? <Check className="w-3.5 h-3.5 text-white" />
                                                : <FolderOpen className="w-3.5 h-3.5 text-app-text-muted" />
                                            }
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <p className={`text-sm truncate leading-tight ${isSelected ? 'font-bold text-app-primary-hover' : 'font-semibold text-app-text-label'}`}>
                                                {project.name || 'Untitled Project'}
                                            </p>
                                            <div className="flex items-center gap-2 mt-0.5">
                                                <span className={`w-1.5 h-1.5 rounded-full ${getStatusColor(project.status)}`}></span>
                                                <span className="text-[11px] text-app-text-light font-medium">{getStatusLabel(project.status)}</span>
                                                {project.documents?.length > 0 && (
                                                    <span className="text-[11px] text-app-text-light">· {project.documents.length} doc{project.documents.length !== 1 ? 's' : ''}</span>
                                                )}
                                            </div>
                                        </div>
                                    </button>
                                );
                            })
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
