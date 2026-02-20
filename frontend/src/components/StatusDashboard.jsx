import React from 'react';
import { Flag, Activity, CheckCircle, Clock, Menu } from 'lucide-react';

export default function StatusDashboard({ isSidebarOpen, onOpenSidebar }) {
    return (
        <div className="w-full h-full bg-gray-50 flex flex-col font-sans overflow-y-auto">
            {/* Top Graphic Header Area */}
            <div className="bg-white shadow">

                {/* Dashboard Title Bar */}
                <div className="bg-[#1c355e] text-white px-4 md:px-8 py-3 flex justify-between items-center rounded-r-full mr-4 md:mr-[60px] my-2 mb-4 shadow-md">
                    <div className="flex items-center gap-4 z-10">
                        {!isSidebarOpen && onOpenSidebar && (
                            <button
                                type="button"
                                onClick={onOpenSidebar}
                                className="p-1.5 md:p-2 bg-white rounded-md shadow-sm text-gray-600 hover:bg-gray-100 hover:text-gray-900 transition-colors border border-gray-200 cursor-pointer flex-shrink-0"
                                aria-label="Open menu"
                            >
                                <Menu className="w-4 h-4 md:w-5 md:h-5" />
                            </button>
                        )}
                        <div>
                            <h1 className="text-xl md:text-3xl font-bold tracking-wide">Assessment Status Dashboard</h1>
                            <h2 className="text-[10px] md:text-sm italic text-gray-200 mt-0.5 md:mt-1">Epic Hub Assessment Report</h2>
                        </div>
                    </div>
                    {/* Status Pipeline graphic top right */}
                    <div className="text-[9px] md:text-xs font-bold text-gray-700 flex items-center space-x-1.5 bg-white px-2 md:px-3 py-1.5 rounded-full shadow-md border border-gray-100 z-20 whitespace-nowrap ml-4 shrink-0 hidden sm:flex translate-x-3 sm:translate-x-5 lg:translate-x-8">
                        <div className="flex items-center"><span className="w-2.5 h-2.5 md:w-3 md:h-3 bg-gray-400 rounded-full mr-1"></span><span className="hidden md:inline">KICK-OFF</span></div>
                        <div className="flex items-center"><span className="w-2.5 h-2.5 md:w-3 md:h-3 bg-orange-200 rounded-full mr-1"></span><span className="hidden md:inline">PREPARE</span></div>
                        <div className="flex items-center"><span className="w-2.5 h-2.5 md:w-3 md:h-3 bg-yellow-400 rounded-full mr-1"></span><span className="hidden md:inline">INTERVIEW</span></div>
                        <div className="flex items-center"><span className="w-2.5 h-2.5 md:w-3 md:h-3 bg-blue-500 rounded-full mr-1"></span><span className="hidden md:inline">APPRAISED</span></div>
                        <div className="flex items-center"><span className="w-2.5 h-2.5 md:w-3 md:h-3 bg-green-500 rounded-full"></span></div>
                    </div>
                </div>

                <div className="flex justify-end px-8 py-1 mb-4 space-x-4">
                    <div className="text-sm font-bold text-[#f27a24]">As of : February 06, 2026</div>
                    <div className="text-sm font-bold text-gray-800 flex items-center">
                        <div className="w-4 h-4 bg-emerald-500 mr-2 rounded-sm shadow-sm inline-block"></div>
                        Overall: On Track
                    </div>
                </div>
            </div>

            <div className="flex-1 p-4 md:p-6 flex flex-col gap-6">

                {/* Top Metric Cards - Full Width */}
                <div className="w-full flex flex-col gap-3 md:gap-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="bg-white p-4 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center relative">
                            <p className="text-xs font-bold text-gray-600 mb-1">Assessment Areas</p>
                            <h3 className="text-3xl font-bold text-gray-800 mb-0">5</h3>
                            <p className="text-[10px] text-gray-500 uppercase tracking-widest">Covered</p>
                        </div>
                        <div className="bg-white p-4 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center relative">
                            <p className="text-xs font-bold text-gray-600 mb-1">Total Duration</p>
                            <h3 className="text-3xl font-bold text-gray-800 mb-0">120</h3>
                            <p className="text-[10px] text-gray-500 uppercase tracking-widest">Days</p>
                        </div>
                        <div className="bg-white col-span-2 md:col-span-2 p-4 rounded-xl shadow border border-gray-100 flex flex-row items-center justify-around relative">
                            <div className="flex flex-col items-center">
                                <p className="text-xs font-bold text-gray-600 mb-1">Documents Received</p>
                                <div className="flex items-center relative">
                                    <h3 className="text-3xl font-bold text-gray-800 mb-0">300+</h3>
                                    <div className="absolute top-0 -right-4 w-3 h-3 select-none text-red-500">✦</div>
                                </div>
                            </div>
                            <div className="w-px h-12 bg-gray-200"></div>
                            <div className="flex flex-col items-center w-40">
                                <p className="text-xs font-bold text-gray-600 mb-1">Documents Reviewed</p>
                                <div className="flex items-center relative mb-2 w-full justify-center">
                                    <h3 className="text-3xl font-bold text-gray-800 mb-0">200+</h3>
                                    <div className="absolute top-0 -right-2 w-3 h-3 select-none text-red-500">✦</div>
                                </div>
                                <div className="w-full bg-gray-200 rounded-full h-2.5">
                                    <div className="bg-gray-800 h-2.5 rounded-full" style={{ width: '66%' }}></div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="grid grid-cols-5 gap-3 mt-4">
                        <div className="bg-white p-3 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center">
                            <p className="text-[11px] font-bold text-gray-600 mb-1">Key Findings</p>
                            <h3 className="text-2xl font-bold text-gray-800">28</h3>
                            <p className="text-[9px] text-gray-500 uppercase tracking-wide">Identified</p>
                        </div>
                        <div className="bg-white p-3 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center">
                            <p className="text-[11px] font-bold text-gray-600 mb-1 text-center leading-tight">High-Risk Areas</p>
                            <h3 className="text-2xl font-bold text-gray-800">3</h3>
                            <p className="text-[9px] text-gray-500 uppercase tracking-wide">Critical</p>
                        </div>
                        <div className="bg-white p-3 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center">
                            <p className="text-[11px] font-bold text-gray-600 mb-1">Open Risks</p>
                            <h3 className="text-2xl font-bold text-gray-800">4</h3>
                            <p className="text-[9px] text-gray-500 uppercase tracking-wide">Active</p>
                        </div>
                        <div className="bg-white p-3 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center">
                            <p className="text-[11px] font-bold text-gray-600 mb-1">Mitigated Risks</p>
                            <h3 className="text-2xl font-bold text-gray-800">0</h3>
                            <p className="text-[9px] text-gray-500 uppercase tracking-wide">Resolved</p>
                        </div>
                        <div className="bg-white p-3 rounded-xl shadow border border-gray-100 flex flex-col items-center justify-center">
                            <p className="text-[11px] font-bold text-gray-600 mb-1">Tasks Identified</p>
                            <h3 className="text-2xl font-bold text-gray-800">143</h3>
                            <p className="text-[9px] text-gray-500 uppercase tracking-wide">Covered</p>
                        </div>
                    </div>
                </div>

                {/* Bottom Section: 2 Columns */}
                <div className="flex flex-col lg:flex-row gap-6 w-full">

                    {/* Left Column (Main Content) */}
                    <div className="flex-1 space-y-6 min-w-0">

                        {/* KEY MILESTONES & DATES */}
                        <div className="bg-white rounded-xl shadow border border-gray-100 p-6 relative">
                            <div className="flex items-center mb-6">
                                <div className="p-2 mr-3 bg-orange-50 rounded text-orange-500">
                                    <Flag className="w-5 h-5" />
                                </div>
                                <h3 className="text-[15px] font-bold text-[#f27a24] uppercase tracking-wide">KEY MILESTONES & DATES</h3>
                            </div>
                            <div className="overflow-hidden rounded-lg">
                                <table className="min-w-full text-sm">
                                    <thead className="bg-[#fdf4e6]">
                                        <tr>
                                            <th className="px-4 py-3 text-left font-bold text-gray-800">Milestone</th>
                                            <th className="px-4 py-3 text-left font-bold text-gray-800">Status</th>
                                            <th className="px-4 py-3 text-left font-bold text-gray-800">Date</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100 text-gray-600 font-medium">
                                        <tr>
                                            <td className="px-4 py-3">Project Kickoff</td>
                                            <td className="px-4 py-3">Completed</td>
                                            <td className="px-4 py-3">Jan 9, 2026</td>
                                        </tr>
                                        <tr>
                                            <td className="px-4 py-3">Tool Deployment & Data Enablement</td>
                                            <td className="px-4 py-3">Completed</td>
                                            <td className="px-4 py-3">Dec 27, 2025</td>
                                        </tr>
                                        <tr>
                                            <td className="px-4 py-3 break-words pr-8">Discovery & Domain Working Sessions (Core Infrastructure, Applications, and Cloud, Security etc)</td>
                                            <td className="px-4 py-3">Completed</td>
                                            <td className="px-4 py-3 whitespace-nowrap">Feb 9, 2026</td>
                                        </tr>
                                        <tr>
                                            <td className="px-4 py-3">Current Infrastructure Assessment</td>
                                            <td className="px-4 py-3">In Progress</td>
                                            <td className="px-4 py-3">Feb 2026</td>
                                        </tr>
                                        <tr>
                                            <td className="px-4 py-3 border-b-0">Assessment Data Consolidation & Validation</td>
                                            <td className="px-4 py-3 border-b-0">In Progress</td>
                                            <td className="px-4 py-3 border-b-0">Feb 2026</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        {/* ACTUAL VS REMAINING WORK */}
                        <div className="bg-white rounded-xl shadow border border-gray-100 p-6 flex flex-col relative min-h-[300px]">
                            <div className="flex items-center mb-8">
                                <div className="p-2 mr-3 bg-orange-50 rounded text-orange-500">
                                    <Activity className="w-5 h-5" />
                                </div>
                                <h3 className="text-[15px] font-bold text-[#f27a24] uppercase tracking-wide">ACTUAL VS REMAINING WORK</h3>
                            </div>

                            <div className="flex-1 flex items-end justify-center px-12 pb-6 relative">
                                {/* Y Axis markings */}
                                <div className="absolute left-10 flex flex-col justify-between h-[200px] bottom-6 text-xs font-bold text-gray-500 w-10 text-right pr-2">
                                    <span className="relative -top-2">80%</span>
                                    <span className="relative">40%</span>
                                    <span className="relative top-2">0%</span>
                                </div>

                                {/* Grid lines */}
                                <div className="absolute left-20 right-40 flex flex-col justify-between h-[200px] bottom-6 pointer-events-none">
                                    <div className="w-full border-t border-gray-300"></div>
                                    <div className="w-full border-t border-gray-300"></div>
                                    <div className="w-full border-t border-gray-500"></div>
                                </div>

                                {/* The Stacked Bar */}
                                <div className="w-[30%] min-w-[150px] relative z-10 flex flex-col justify-end">
                                    {/* Remaining Work (60%) */}
                                    <div className="bg-[#feebad] w-full h-[120px] relative flex items-center justify-center">
                                        <span className="text-orange-500 font-bold text-sm">60%</span>
                                    </div>
                                    {/* Work (40%) */}
                                    <div className="bg-[#424242] w-full h-[80px] relative flex items-center justify-center">
                                        <span className="text-white font-bold text-sm">40%</span>
                                    </div>
                                </div>

                                <div className="absolute bottom-[-15px] w-full text-center text-[10px] font-bold text-gray-500">
                                    Overall Assessment Progress
                                </div>

                                {/* Legend */}
                                <div className="absolute right-10 bottom-20 flex flex-col gap-3">
                                    <div className="flex items-center">
                                        <div className="w-6 h-4 bg-[#feebad] mr-3"></div>
                                        <span className="text-sm text-gray-700 font-medium">Remaining Work</span>
                                    </div>
                                    <div className="flex items-center">
                                        <div className="w-6 h-4 bg-[#424242] mr-3"></div>
                                        <span className="text-sm text-gray-700 font-medium">Work</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* 5 Key Assessment Areas & progress */}
                        <div className="bg-white rounded-xl shadow border border-gray-100 p-6">
                            <div className="flex items-center mb-8">
                                <div className="p-2 mr-3 bg-orange-50 rounded text-orange-500">
                                    <CheckCircle className="w-5 h-5" />
                                </div>
                                <h3 className="text-[15px] font-bold text-[#f27a24] uppercase tracking-wide">5 Key Assessment Areas & progress</h3>
                            </div>

                            <div className="space-y-6">
                                {/* Bar 1 */}
                                <div className="flex items-center">
                                    <div className="w-48 text-xs font-bold text-gray-800 flex items-center">
                                        <div className="mr-2 opacity-60"><Clock className="w-4 h-4" /></div>
                                        Infrastructure Assessment
                                    </div>
                                    <div className="flex-1 right-0 relative flex flex-col justify-center">
                                        <div className="text-right text-[10px] font-bold text-gray-800 mb-1 absolute -top-4 right-0">60%</div>
                                        <div className="w-full bg-[#fceacc] rounded-full h-3 flex overflow-hidden">
                                            <div className="bg-[#ea7032] h-full" style={{ width: '60%' }}></div>
                                        </div>
                                    </div>
                                </div>

                                {/* Bar 2 */}
                                <div className="flex items-center">
                                    <div className="w-48 text-xs font-bold text-gray-800 flex items-center">
                                        <div className="mr-2 opacity-60"><Clock className="w-4 h-4" /></div>
                                        Application Dependency Map
                                    </div>
                                    <div className="flex-1 right-0 relative flex flex-col justify-center">
                                        <div className="text-right text-[10px] font-bold text-gray-800 mb-1 absolute -top-4 right-0">10%</div>
                                        <div className="w-full bg-[#fdf4e6] rounded-full h-3 flex overflow-hidden">
                                            <div className="bg-[#feebad] h-full" style={{ width: '10%' }}></div>
                                        </div>
                                    </div>
                                </div>

                                {/* Bar 3 */}
                                <div className="flex items-center">
                                    <div className="w-48 text-xs font-bold text-gray-800 flex items-center">
                                        <div className="mr-2 opacity-60"><Clock className="w-4 h-4" /></div>
                                        Security & Compliance
                                    </div>
                                    <div className="flex-1 right-0 relative flex flex-col justify-center">
                                        <div className="text-right text-[10px] font-bold text-gray-800 mb-1 absolute -top-4 right-0">60%</div>
                                        <div className="w-full bg-[#e0e0e0] rounded-full h-3 flex overflow-hidden">
                                            <div className="bg-[#6b6b6b] h-full" style={{ width: '60%' }}></div>
                                        </div>
                                    </div>
                                </div>

                                {/* Bar 4 */}
                                <div className="flex items-center">
                                    <div className="w-48 text-xs font-bold text-gray-800 flex items-center">
                                        <div className="mr-2 opacity-60"><Clock className="w-4 h-4" /></div>
                                        End User Computing
                                    </div>
                                    <div className="flex-1 right-0 relative flex flex-col justify-center">
                                        <div className="text-right text-[10px] font-bold text-gray-800 mb-1 absolute -top-4 right-0">60%</div>
                                        <div className="w-full bg-[#d0e0fb] rounded-full h-3 flex overflow-hidden">
                                            <div className="bg-[#0c2e64] h-full" style={{ width: '60%' }}></div>
                                        </div>
                                    </div>
                                </div>

                                {/* Bar 5 */}
                                <div className="flex items-center">
                                    <div className="w-48 text-xs font-bold text-gray-800 flex items-center">
                                        <div className="mr-2 opacity-60"><Clock className="w-4 h-4" /></div>
                                        Performance & Cost Baseline
                                    </div>
                                    <div className="flex-1 right-0 relative flex flex-col justify-center">
                                        <div className="text-right text-[10px] font-bold text-gray-800 mb-1 absolute -top-4 right-0">10%</div>
                                        <div className="w-full bg-[#fdf4e6] rounded-full h-3 flex overflow-hidden">
                                            <div className="bg-[#feebad] h-full" style={{ width: '10%' }}></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Right Column (Sidebar Summary) */}
                    <div className="w-full shrink-0 lg:w-[320px] bg-white rounded-xl shadow border border-gray-100 p-4 md:p-6 flex flex-col items-center">
                        <h2 className="text-[22px] font-bold text-[#f27a24] mb-4">Project Status</h2>
                        <div className="w-full border-t-2 border-[#f27a24] mb-8 opacity-50"></div>

                        <div className="w-full mb-10 flex flex-col items-center relative">
                            <div className="absolute left-[-5px] top-0 text-green-500">
                                <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"></path></svg>
                            </div>
                            <div className="bg-white border rounded p-4 text-center w-5/6 mx-auto shadow-sm relative z-10">
                                <p className="text-[10px] font-bold text-gray-800 uppercase mb-2">EXPECTED LAUNCH DATE</p>
                                <h3 className="text-2xl font-black text-gray-900 mb-2">50 <span className="text-sm font-medium">Days</span></h3>
                                <div className="flex items-center justify-center w-full mb-2">
                                    <div className="h-px bg-gray-300 w-full relative">
                                        <div className="absolute left-0 top-[-3px] w-2 h-2 bg-gray-400 rounded-full"></div>
                                        <div className="absolute right-0 top-[-3px] w-2 h-2 bg-gray-400 rounded-full"></div>
                                    </div>
                                </div>
                                <p className="text-xs italic text-gray-500">Tuesday, 31 March 2026</p>
                            </div>
                        </div>

                        <div className="w-full mb-10 flex flex-col items-center">
                            <div className="flex justify-center items-center w-full relative mb-1">
                                <div className="absolute left-8 text-green-500">
                                    <Activity className="w-8 h-8" />
                                </div>
                                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-green-400 to-green-600 shadow-lg shadow-green-500/30"></div>
                            </div>
                            <p className="text-sm font-bold text-gray-800 mt-2">Overall, Health</p>
                        </div>

                        <div className="w-full border-t border-gray-100 mb-8 w-4/5 mx-auto"></div>

                        {/* Circular Gauge 1 */}
                        <div className="mb-10 flex flex-col items-center relative w-full">
                            <div className="absolute left-8 text-orange-200">
                                <svg className="w-8 h-8 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"></path></svg>
                            </div>
                            <div className="relative w-24 h-24 mb-4">
                                <svg className="w-24 h-24 transform -rotate-90">
                                    <circle cx="48" cy="48" r="40" stroke="#fdf4e6" strokeWidth="12" fill="none" />
                                    <circle cx="48" cy="48" r="40" stroke="#f27a24" strokeWidth="12" fill="none" strokeDasharray="251" strokeDashoffset="125.5" strokeLinecap="round" />
                                </svg>
                                <div className="absolute inset-0 flex items-center justify-center">
                                    <span className="text-xl font-bold text-gray-800">50%</span>
                                </div>
                            </div>
                            <p className="text-[13px] font-bold text-gray-600">Decision Readiness</p>
                        </div>

                        <div className="w-full border-t border-gray-100 mb-8 w-4/5 mx-auto"></div>

                        {/* Circular Gauge 2 */}
                        <div className="mb-10 flex flex-col items-center relative w-full">
                            <div className="absolute left-8 text-gray-300">
                                <svg className="w-6 h-6 opacity-70" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"></path></svg>
                            </div>
                            <div className="relative w-24 h-24 mb-4">
                                <svg className="w-24 h-24 transform -rotate-90">
                                    <circle cx="48" cy="48" r="40" stroke="#f3f4f6" strokeWidth="12" fill="none" />
                                    <circle cx="48" cy="48" r="40" stroke="#9ca3af" strokeWidth="12" fill="none" strokeDasharray="251" strokeDashoffset="150.6" strokeLinecap="round" />
                                </svg>
                                <div className="absolute inset-0 flex items-center justify-center">
                                    <span className="text-xl font-bold text-gray-800">40%</span>
                                </div>
                            </div>
                            <p className="text-[13px] font-bold text-gray-600">Project Progress</p>
                        </div>

                        <div className="w-full border-t border-gray-100 mb-8 w-4/5 mx-auto"></div>

                        {/* Circular Gauge 3 */}
                        <div className="mb-6 flex flex-col items-center relative w-full">
                            <div className="absolute left-6 text-gray-700">
                                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2"></path></svg>
                            </div>
                            <div className="relative w-24 h-24 mb-4">
                                <svg className="w-24 h-24 transform -rotate-90">
                                    <circle cx="48" cy="48" r="40" stroke="#f3f4f6" strokeWidth="12" fill="none" />
                                    <circle cx="48" cy="48" r="40" stroke="#1f2937" strokeWidth="12" fill="none" strokeDasharray="251" strokeDashoffset="50.2" strokeLinecap="round" />
                                </svg>
                                <div className="absolute inset-0 flex items-center justify-center">
                                    <span className="text-xl font-bold text-gray-800">80%</span>
                                </div>
                            </div>
                            <p className="text-[13px] font-bold text-gray-600">Phase Progress</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
