import { useRef, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import {
    ArrowRight, Zap, CheckCircle, Smartphone, Globe, Shield,
    FileText, FileCode, FileSpreadsheet, FileJson, File,
    Database, Server, Layout, Code, Terminal, Cpu
} from 'lucide-react';
import Logo from '../assets/logo.png';
import Login from './Login';
import Signup from './Signup';

gsap.registerPlugin(ScrollTrigger);

const MarqueeRow = ({ reverse = false, duration = 40, iconColor = "text-slate-400" }) => {
    // Icons set
    const icons = [FileText, FileCode, FileSpreadsheet, FileJson, File, Database, Server, Layout, Code, Terminal, Cpu];

    // Duplicate for seamless loop - enough width for wide screens
    // 11 icons * 3 = 33 icons total which ensures enough coverage
    const items = [...icons, ...icons, ...icons];

    const animationStyle = {
        animation: reverse
            ? `marquee-reverse ${duration}s linear infinite`
            : `marquee ${duration}s linear infinite`,
        willChange: 'transform',
        backfaceVisibility: 'hidden',
    };

    return (
        <div className="overflow-hidden whitespace-nowrap w-full pointer-events-none select-none">
            <div className="flex w-max" style={animationStyle}>
                <div className="flex gap-8 px-4 w-max shrink-0">
                    {items.map((Icon, idx) => (
                        <div key={`a-${idx}`} className={`flex items-center justify-center h-16 w-16 bg-white rounded-xl border border-slate-200/50 shadow-sm ${iconColor}`}>
                            <Icon className="h-8 w-8 opacity-80" strokeWidth={1.5} />
                        </div>
                    ))}
                </div>
                <div className="flex gap-8 px-4 w-max shrink-0">
                    {items.map((Icon, idx) => (
                        <div key={`b-${idx}`} className={`flex items-center justify-center h-16 w-16 bg-white rounded-xl border border-slate-200/50 shadow-sm ${iconColor}`}>
                            <Icon className="h-8 w-8 opacity-80" strokeWidth={1.5} />
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

const BackgroundMarquee = () => {
    return (
        <div className="fixed inset-0 z-0 overflow-hidden bg-slate-50 pointer-events-none">
            <div className="absolute inset-0 flex flex-col gap-10 -rotate-12 scale-150 origin-center justify-center opacity-40">
                <MarqueeRow duration={55} iconColor="text-blue-400" />
                <MarqueeRow duration={65} reverse iconColor="text-slate-400" />
                <MarqueeRow duration={50} iconColor="text-indigo-400" />
                <MarqueeRow duration={70} reverse iconColor="text-slate-400" />
                <MarqueeRow duration={60} iconColor="text-blue-400" />
                <MarqueeRow duration={68} reverse iconColor="text-slate-400" />
                <MarqueeRow duration={58} iconColor="text-indigo-400" />
            </div>
            <div className="absolute inset-0 bg-gradient-to-br from-white/95 via-white/40 to-white/95 backdrop-blur-[1px]"></div>
        </div>
    );
};

const LandingPage = () => {
    const heroRef = useRef(null);
    const featuresRef = useRef(null);
    const ctaRef = useRef(null);
    const [isLoginOpen, setIsLoginOpen] = useState(false);
    const [isSignupOpen, setIsSignupOpen] = useState(false);

    const openLogin = () => {
        setIsSignupOpen(false);
        setIsLoginOpen(true);
    };

    const openSignup = () => {
        setIsLoginOpen(false);
        setIsSignupOpen(true);
    };

    const closeModals = () => {
        setIsLoginOpen(false);
        setIsSignupOpen(false);
    };

    useEffect(() => {
        const ctx = gsap.context(() => {
            // Hero Animations
            gsap.from('.hero-content > *', {
                y: 30,
                opacity: 0,
                duration: 0.8,
                stagger: 0.1,
                ease: 'power2.out',
                clearProps: 'all'
            });

            gsap.from('.hero-image', {
                x: 30,
                opacity: 0,
                duration: 1,
                delay: 0.3,
                ease: 'power2.out',
                clearProps: 'all'
            });

            // Features Animations
            gsap.from('.feature-card', {
                scrollTrigger: {
                    trigger: featuresRef.current,
                    start: 'top bottom-=100',
                    toggleActions: 'play none none reverse'
                },
                y: 30,
                opacity: 0,
                duration: 0.6,
                stagger: 0.1,
                ease: 'power2.out'
            });
        });

        return () => ctx.revert();
    }, []);

    // Prevent body scroll when modal is open
    useEffect(() => {
        if (isLoginOpen || isSignupOpen) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = 'auto';
        }
        return () => {
            document.body.style.overflow = 'auto';
        };
    }, [isLoginOpen, isSignupOpen]);

    return (
        <div className="min-h-screen text-slate-900 font-sans overflow-x-hidden relative">
            <BackgroundMarquee />

            {/* Navigation */}
            <nav className="fixed w-full bg-white/90 backdrop-blur-md z-50 border-b border-slate-100 transition-all duration-300">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex justify-between items-center h-16">
                        <div className="flex items-center gap-3">
                            <img src={Logo} alt="BRD Analyzer" className="h-10 w-auto" />
                            <div className="h-6 w-px bg-slate-200"></div>
                            <span className="text-xl font-bold tracking-tight text-slate-900">BRD Analyzer</span>
                        </div>
                        <div className="flex items-center gap-4">
                            <button
                                onClick={openLogin}
                                className="text-slate-600 hover:text-slate-900 font-medium transition-colors cursor-pointer bg-transparent border-0"
                            >
                                Log in
                            </button>
                            <button
                                onClick={openSignup}
                                className="hidden sm:inline-flex bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-lg font-semibold transition-transform hover:scale-105 shadow-md shadow-blue-500/20 cursor-pointer border-0"
                            >
                                Get Started
                            </button>
                        </div>
                    </div>
                </div>
            </nav>

            {/* Hero Section */}
            <section ref={heroRef} className="pt-32 pb-6 lg:pt-48 lg:pb-12 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto relative z-10">
                <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
                    <div className="hero-content space-y-6 lg:space-y-8 text-center lg:text-left">
                        <div className="inline-flex items-center gap-2 px-3 py-1 bg-blue-50 border border-blue-100 rounded-full text-blue-600 text-xs font-semibold mx-auto lg:mx-0">
                            <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                            </span>
                            AI-Powered Analysis v1.0
                        </div>
                        <h1 className="text-4xl sm:text-5xl lg:text-7xl font-extrabold tracking-tight leading-tight text-slate-900">
                            Transform <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600">Docs</span> into Intelligence
                        </h1>
                        <p className="text-lg sm:text-xl text-slate-600 leading-relaxed max-w-lg mx-auto lg:mx-0">
                            Instantly analyze Business Requirement Documents (BRDs) with advanced AI. Get feasibility checks and technical insights in seconds.
                        </p>
                        <div className="flex flex-col sm:flex-row gap-4 pt-4 justify-center lg:justify-start">
                            <button
                                onClick={openSignup}
                                className="inline-flex justify-center items-center px-8 py-4 text-base font-bold text-white bg-blue-600 rounded-xl hover:bg-blue-700 transition-all shadow-lg hover:shadow-xl hover:-translate-y-0.5 active:translate-y-0 cursor-pointer border-0"
                            >
                                Start Analysis Free
                                <ArrowRight className="ml-2 h-5 w-5" />
                            </button>
                            <a
                                href="#features"
                                className="inline-flex justify-center items-center px-8 py-4 text-base font-bold text-slate-700 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors"
                            >
                                How it works
                            </a>
                        </div>
                        <div className="flex flex-wrap justify-center lg:justify-start gap-4 pt-4 text-sm text-slate-500">
                            <div className="flex items-center gap-1">
                                <CheckCircle className="h-4 w-4 text-green-500 shrink-0" />
                                <span>No credit card required</span>
                            </div>
                            <div className="flex items-center gap-1">
                                <CheckCircle className="h-4 w-4 text-green-500 shrink-0" />
                                <span>Enterprise-grade security</span>
                            </div>
                        </div>
                    </div>

                    <div className="hero-image relative mt-8 lg:mt-0">
                        <div className="absolute -inset-4 bg-gradient-to-r from-blue-100 to-indigo-100 rounded-3xl blur-2xl opacity-40"></div>
                        <div className="relative bg-white border border-slate-200 rounded-2xl shadow-xl overflow-hidden">
                            <div className="bg-slate-50 p-4 sm:p-6 min-h-[400px] flex flex-col gap-4">
                                <div className="h-8 w-1/3 bg-slate-200 rounded animate-pulse"></div>
                                <div className="h-24 w-full bg-white rounded-lg border border-slate-200 shadow-sm p-4 space-y-2">
                                    <div className="h-3 w-3/4 bg-slate-100 rounded"></div>
                                    <div className="h-3 w-1/2 bg-slate-100 rounded"></div>
                                </div>
                                <div className="flex-1 bg-white rounded-lg border border-slate-200 shadow-sm p-4 space-y-4">
                                    <div className="flex items-center gap-3 mb-4">
                                        <div className="h-8 w-8 bg-blue-100 rounded-full flex items-center justify-center shrink-0">
                                            <Zap className="h-4 w-4 text-blue-600" />
                                        </div>
                                        <div className="h-3 w-1/4 bg-slate-100 rounded"></div>
                                    </div>
                                    <div className="space-y-3">
                                        {[1, 2, 3].map((i) => (
                                            <div key={i} className="flex gap-3">
                                                <div className="h-2 w-2 mt-1.5 bg-green-400 rounded-full shrink-0"></div>
                                                <div className="h-2 w-full bg-slate-50 rounded"></div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Features Section */}
            <section id="features" ref={featuresRef} className="py-10 bg-white/60 backdrop-blur-sm relative z-10 border-t border-slate-100">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="text-center max-w-3xl mx-auto mb-12">
                        <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl mb-4">
                            Everything you need
                        </h2>
                        <p className="text-lg text-slate-600">
                            Comprehensive technical breakdowns from your requirements.
                        </p>
                    </div>

                    <div className="grid md:grid-cols-3 gap-8">
                        {[
                            {
                                icon: <Smartphone className="h-6 w-6 text-white" />,
                                title: "Instant Analysis",
                                desc: "Upload and get a complete breakdown in seconds.",
                                color: "bg-blue-500"
                            },
                            {
                                icon: <Shield className="h-6 w-6 text-white" />,
                                title: "Security First",
                                desc: "Encryption and secure processing environment.",
                                color: "bg-indigo-500"
                            },
                            {
                                icon: <Globe className="h-6 w-6 text-white" />,
                                title: "Global Standards",
                                desc: "Analysis based on industry best practices.",
                                color: "bg-purple-500"
                            }
                        ].map((feature, idx) => (
                            <div key={idx} className="feature-card bg-white p-6 rounded-2xl shadow-sm border border-slate-100 hover:shadow-md transition-shadow">
                                <div className={`h-12 w-12 ${feature.color} rounded-xl flex items-center justify-center mb-4 shadow-md shadow-blue-500/10`}>
                                    {feature.icon}
                                </div>
                                <h3 className="text-lg font-bold text-slate-900 mb-2">{feature.title}</h3>
                                <p className="text-slate-600 text-sm leading-relaxed">
                                    {feature.desc}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA Section */}
            <section className="py-20 px-4 sm:px-6 lg:px-8 relative z-10">
                <div ref={ctaRef} className="max-w-5xl mx-auto bg-slate-900 rounded-3xl overflow-hidden relative shadow-2xl">
                    <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-10 mix-blend-overlay"></div>
                    <div className="absolute -top-24 -right-24 w-96 h-96 bg-blue-600/30 rounded-full blur-3xl"></div>
                    <div className="absolute -bottom-24 -left-24 w-96 h-96 bg-purple-600/30 rounded-full blur-3xl"></div>

                    <div className="relative px-6 py-12 md:px-12 md:py-16 text-center">
                        <h2 className="text-2xl md:text-4xl font-bold text-white mb-4 tracking-tight">
                            Ready to clean up your docs?
                        </h2>
                        <p className="text-slate-300 text-base md:text-lg max-w-xl mx-auto mb-8">
                            Join thousands of developers using BRD Analyzer today.
                        </p>
                        <button
                            onClick={openSignup}
                            className="inline-flex justify-center items-center px-8 py-3.5 text-base font-bold text-slate-900 bg-white rounded-xl hover:bg-slate-50 transition-colors shadow-lg active:scale-95 cursor-pointer border-0"
                        >
                            Get Started for Free
                            <ArrowRight className="ml-2 h-5 w-5" />
                        </button>
                    </div>
                </div>
            </section>

            {/* Footer */}
            <footer className="bg-white border-t border-slate-100 py-8 relative z-10">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center text-slate-400 text-sm">
                    <p>© 2024 BRD Analyzer. All rights reserved.</p>
                </div>
            </footer>

            {/* Modals */}
            {(isLoginOpen || isSignupOpen) && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
                    <div
                        className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity opacity-100"
                        onClick={closeModals}
                    ></div>
                    <div className="relative z-10 w-full max-w-md bg-transparent">
                        {isLoginOpen && <Login isModal onClose={closeModals} onSwitch={openSignup} />}
                        {isSignupOpen && <Signup isModal onClose={closeModals} onSwitch={openLogin} />}
                    </div>
                </div>
            )}
        </div>
    );
};

export default LandingPage;
