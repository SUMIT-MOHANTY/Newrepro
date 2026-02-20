import React from 'react';
import { MapPin } from 'lucide-react';

const RoadmapHeader = ({ steps, currentStep }) => {
    return (
        <div className="w-full py-6 sm:py-8 lg:py-10 mb-8 overflow-x-auto scrollbar-hide">
            <div className="relative min-w-[600px] px-4 mx-auto max-w-6xl">

                {/* ── Dashed Line ── */}
                <div
                    className="absolute left-0 w-full border-t-2 border-gray-400 border-dashed"
                    style={{ top: '50px' }}
                />

                <div className="flex justify-between items-start w-full relative">
                    {steps.map((step, index) => {
                        const isActive = index === currentStep;
                        const isCompleted = index <= currentStep;

                        return (
                            <div key={index} className="flex flex-col items-center group relative z-10">

                                {/* Pin Icon Container - Fixed Height for alignment */}
                                <div className={`flex items-end justify-center h-10 mb-2 transition-transform duration-500 ease-out
                                    ${isActive ? 'scale-110 -translate-y-1' : 'scale-100'}
                                `}>
                                    <MapPin
                                        className={`w-8 h-8 sm:w-9 sm:h-9 fill-current drop-shadow-sm transition-colors duration-300
                                            ${isCompleted ? 'text-[#DC2626]' : 'text-gray-300'}
                                        `}
                                        stroke="white"
                                        strokeWidth={1.5}
                                    />
                                </div>

                                {/* Dot on the line */}
                                <div
                                    className={`w-3 h-3 rounded-full border-2 border-white shadow-sm transition-colors duration-300
                                        ${isCompleted ? 'bg-[#DC2626]' : 'bg-gray-300'}
                                    `}
                                />

                                {/* Step Label */}
                                <div className={`mt-3 text-center transition-opacity duration-300
                                    ${isActive ? 'opacity-100' : 'opacity-70'}
                                `}>
                                    <p className={`text-[10px] sm:text-xs font-bold uppercase tracking-wider mb-0.5
                                        ${isCompleted ? 'text-[#DC2626]' : 'text-gray-400'}
                                    `}>
                                        Step {index + 1}
                                    </p>
                                    <p className={`text-[10px] sm:text-xs font-medium max-w-[80px] leading-tight mx-auto
                                        ${isCompleted ? 'text-gray-900' : 'text-gray-400'}
                                    `}>
                                        {step}
                                    </p>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
};

export default RoadmapHeader;
