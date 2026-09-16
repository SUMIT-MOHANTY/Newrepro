import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Users, Check } from 'lucide-react';

export default function RoleDropdown({ roles = [], selectedRole, onSelect, className = '', theme = 'light' }) {
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef(null);

    const selectedRoleData = roles.find(r => r.value === selectedRole) || null;

    // Close on outside click
    useEffect(() => {
        const handleClickOutside = (e) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    return (
        <div ref={dropdownRef} className={`relative ${className}`}>
            {/* Trigger Button */}
            <button
                type="button"
                onClick={() => setIsOpen(!isOpen)}
                title={selectedRoleData?.label || 'Select Role'}
                className={`
                    w-full flex items-center justify-between gap-1 sm:gap-1.5
                    ${theme === 'dark'
                        ? 'bg-transparent hover:bg-white/5 rounded-md px-1.5 sm:px-2 py-0.5 sm:py-1'
                        : 'bg-app-bg-card border-2 border-app-border hover:border-app-border rounded-xl px-3 py-2'
                    }
                    text-xs sm:text-sm font-semibold
                    shadow-sm
                    transition-all duration-200 ease-in-out
                    focus:outline-none focus:ring-2 focus:ring-white/20
                    ${isOpen && theme === 'dark' ? 'bg-white/10' : ''}
                    ${isOpen && theme !== 'dark' ? 'border-blue-400 ring-4 ring-app-primary-light shadow-md' : ''}
                `}
            >
                <div className="flex items-center gap-1.5 min-w-0">
                    <div className={`w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0 shadow-sm ${theme === 'dark' ? 'bg-white/10' : 'bg-gradient-to-br from-app-primary to-app-primary'}`}>
                        <Users className={`w-3 h-3 ${theme === 'dark' ? 'text-white' : 'text-app-bg-card'}`} />
                    </div>
                    <div className="text-left min-w-0">
                        <p className={`text-[9px] font-medium leading-none mb-0.5 ${theme === 'dark' ? 'text-white/70' : 'text-app-text-light'}`}>Role</p>
                        <p className={`text-[11px] sm:text-xs font-bold truncate leading-tight ${theme === 'dark' ? 'text-white' : 'text-app-text-main'}`}>
                            {selectedRoleData?.shortLabel || selectedRoleData?.label || 'Select Role'}
                        </p>
                    </div>
                </div>
                <ChevronDown className={`w-3 h-3 flex-shrink-0 transition-transform duration-200 ${theme === 'dark' ? 'text-white/70' : 'text-app-text-light'} ${isOpen ? 'rotate-180' : ''}`} />
            </button>

            {/* Dropdown Panel */}
            {isOpen && (
                <div className="absolute top-full left-0 right-0 sm:right-auto sm:min-w-[240px] mt-2 z-50
                    bg-app-bg-card rounded-xl border border-app-border shadow-xl
                    overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150 py-1.5"
                    style={{ maxHeight: '340px' }}
                >
                    {/* Options List */}
                    <div className="overflow-y-auto" style={{ maxHeight: '270px' }}>
                        {roles.map((role) => {
                            const isSelected = role.value === selectedRole;
                            return (
                                <button
                                    key={role.value}
                                    type="button"
                                    onClick={() => {
                                        onSelect(role.value);
                                        setIsOpen(false);
                                    }}
                                    className={`
                                        w-full flex items-center gap-3 px-3 py-2 text-left
                                        transition-colors duration-100
                                        ${isSelected
                                            ? 'bg-app-primary-light/50 border-l-3 border-l-blue-500'
                                            : 'hover:bg-app-bg-hover border-l-3 border-l-transparent'
                                        }
                                    `}
                                >
                                    <div className="flex-1 min-w-0">
                                        <p className={`text-sm truncate leading-tight ${isSelected ? 'font-bold text-app-primary-hover' : 'font-semibold text-app-text-label'}`}>
                                            {role.label}
                                        </p>
                                        <p className="text-[10px] text-app-text-light truncate mt-0.5">
                                            {role.description}
                                        </p>
                                    </div>
                                    {isSelected && <Check className="w-3.5 h-3.5 text-app-primary flex-shrink-0" />}
                                </button>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}
