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

const MarqueeRow = ({ reverse = false, duration = 40, iconColor = "text-app-text-light" }) => {
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
                        <div key={`a-${idx}`} className={`flex items-center justify-center h-16 w-16 bg-app-bg-card rounded-xl border border-app-border/50 shadow-sm ${iconColor}`}>
                            <Icon className="h-8 w-8 opacity-80" strokeWidth={1.5} />
                        </div>
                    ))}
                </div>
                <div className="flex gap-8 px-4 w-max shrink-0">
                    {items.map((Icon, idx) => (
                        <div key={`b-${idx}`} className={`flex items-center justify-center h-16 w-16 bg-app-bg-card rounded-xl border border-app-border/50 shadow-sm ${iconColor}`}>
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
        <div className="fixed inset-0 z-0 overflow-hidden bg-app-bg-page pointer-events-none" style={{ transform: "translateZ(0)" }}>
            <div className="absolute inset-0 flex flex-col gap-12 -rotate-12 scale-150 origin-center justify-center opacity-20" style={{ willChange: "transform" }}>
                <MarqueeRow duration={55} iconColor="text-blue-400/50" />
                <MarqueeRow duration={65} reverse iconColor="text-app-text-light/50" />
                <MarqueeRow duration={50} iconColor="text-indigo-400/50" />
                <MarqueeRow duration={70} reverse iconColor="text-app-text-light/50" />
            </div>
            <div className="absolute inset-0 bg-gradient-to-br from-white/95 via-white/60 to-white/95"></div>
        </div>
    );
};

const HeroInteractiveImage = () => {
    const containerRef = useRef(null);

    const handleMouseMove = (e) => {
        if (!containerRef.current) return;
        const rect = containerRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left - rect.width / 2;
        const y = e.clientY - rect.top - rect.height / 2;

        // Calculate rotation amounts - very subtle tilt
        const xRotation = (-y / (rect.height / 2)) * 6;
        const yRotation = (x / (rect.width / 2)) * 6;

        containerRef.current.style.transform = `perspective(1000px) rotateX(${xRotation}deg) rotateY(${yRotation}deg) scale3d(1.02, 1.02, 1.02)`;
    };

    const handleMouseLeave = () => {
        if (!containerRef.current) return;
        containerRef.current.style.transform = `perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)`;
    };

    return (
        <div
            className="relative w-full aspect-square sm:aspect-[4/3] lg:aspect-square flex items-center justify-center p-4 sm:p-8 shrink-0 z-10"
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
            style={{ perspective: "1000px" }}
        >
            <div
                ref={containerRef}
                className="relative w-full h-full transition-transform duration-200 ease-out will-change-transform"
                style={{ transformStyle: "preserve-3d" }}
            >
                {/* Background Window - Technical Breakdown */}
                <div className="absolute inset-0 bg-app-bg-card/95 border border-white/5 rounded-2xl shadow-xl overflow-hidden flex flex-col" style={{ transform: "translateZ(0px)" }}>
                    <div className="h-10 border-b border-app-border-light flex items-center px-4 gap-2 bg-app-bg-page/80 shrink-0">
                        <div className="w-3 h-3 rounded-full bg-red-400"></div>
                        <div className="w-3 h-3 rounded-full bg-yellow-400"></div>
                        <div className="w-3 h-3 rounded-full bg-green-400"></div>
                        <div className="flex-1 text-center text-xs text-app-text-muted font-mono tracking-widest">system_architecture.json</div>
                    </div>
                    <div className="p-6 space-y-5 flex-1 overflow-hidden bg-[linear-gradient(rgba(0,0,0,.02)_1px,transparent_1px),linear-gradient(90deg,rgba(0,0,0,.02)_1px,transparent_1px)] bg-[size:20px_20px]">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-full bg-blue-500/10 flex items-center justify-center border border-blue-500/20">
                                    <Cpu className="w-5 h-5 text-blue-500" />
                                </div>
                                <div>
                                    <h3 className="text-sm font-semibold text-app-text-main">Analysis Complete</h3>
                                    <p className="text-xs text-app-text-muted">9 entities extracted</p>
                                </div>
                            </div>
                            <span className="px-2 py-1 rounded-md bg-green-500/10 text-green-500 text-[10px] sm:text-xs font-mono font-semibold border border-green-500/20">200 OK</span>
                        </div>

                        <div className="space-y-3">
                            <div className="flex justify-between items-center bg-app-bg-page/50 p-3 rounded-xl border border-app-border shadow-sm">
                                <div className="flex items-center gap-3">
                                    <Database className="w-4 h-4 text-indigo-500" />
                                    <span className="text-sm text-app-text-main font-medium">PostgreSQL Schema</span>
                                </div>
                                <span className="text-[10px] uppercase text-indigo-500 bg-indigo-500/10 px-2 py-1 rounded font-bold tracking-wider">Ready</span>
                            </div>
                            <div className="flex justify-between items-center bg-app-bg-page/50 p-3 rounded-xl border border-app-border shadow-sm">
                                <div className="flex items-center gap-3">
                                    <Server className="w-4 h-4 text-purple-500" />
                                    <span className="text-sm text-app-text-main font-medium">REST API Routes</span>
                                </div>
                                <span className="text-[10px] uppercase text-purple-500 bg-purple-500/10 px-2 py-1 rounded font-bold tracking-wider">Ready</span>
                            </div>
                            <div className="flex justify-between items-center bg-app-bg-page/50 p-3 rounded-xl border border-app-border shadow-sm opacity-60">
                                <div className="flex items-center gap-3">
                                    <Layout className="w-4 h-4 text-pink-500" />
                                    <span className="text-sm text-app-text-main font-medium">React Components</span>
                                </div>
                                <span className="text-[10px] uppercase text-app-text-muted bg-app-bg-hover px-2 py-1 rounded font-bold tracking-wider">Pending</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Floating Foreground Card - Document input */}
                <div
                    className="absolute -right-2 sm:-right-8 -bottom-4 sm:-bottom-8 w-56 sm:w-64 bg-app-bg-page/95 border border-app-border-light p-4 sm:p-5 rounded-2xl shadow-2xl"
                    style={{ transform: "translateZ(60px)" }}
                >
                    <div className="flex items-center gap-3 border-b border-app-border-light pb-3 mb-3 shrink-0">
                        <div className="p-2 sm:p-2.5 bg-blue-500/10 rounded-xl border border-blue-500/20 shrink-0">
                            <FileText className="w-5 h-5 text-blue-500" />
                        </div>
                        <div className="overflow-hidden">
                            <div className="text-sm font-bold text-app-text-main truncate">Project_Alpha_BRD.pdf</div>
                            <div className="text-xs text-blue-500 font-semibold mt-0.5">Processing... 84%</div>
                        </div>
                    </div>
                    <div className="space-y-3">
                        <div className="h-1.5 w-full bg-app-bg-hover rounded-full overflow-hidden">
                            <div className="h-full bg-gradient-to-r from-blue-600 to-cyan-400 w-[84%] rounded-full relative">
                                <div className="absolute inset-0 w-full animate-pulse bg-white/30"></div>
                            </div>
                        </div>
                        <p className="text-xs text-app-text-muted truncate">Extracting logic constraints...</p>
                    </div>
                </div>

                {/* Floating API Endpoint */}
                <div
                    className="absolute -left-2 sm:-left-8 top-12 bg-app-bg-card border border-app-border-light p-3 rounded-xl shadow-xl font-mono text-[10px] sm:text-xs flex flex-col gap-1.5"
                    style={{ transform: "translateZ(30px)" }}
                >
                    <div className="text-app-text-main flex items-center gap-2">
                        <span className="text-green-500 font-bold bg-green-500/10 px-1.5 py-0.5 rounded">POST</span>
                        /api/v1/auth
                    </div>
                    <div className="text-app-text-muted pl-4 border-l border-app-border-light ml-2 mt-1 py-1">
                        {'{ "role": "admin" }'}
                    </div>
                </div>
            </div>
        </div>
    );
};

const Interactive3DScroll = () => {
    const wrapperRef = useRef(null);

    const steps = [
        {
            title: "Upload & Extract",
            desc: "Drag and drop your unstructured BRDs. Our engine immediately gets to work extracting key entities, requirements, and constraints.",
            icon: <FileText className="h-16 w-16 text-blue-500" />,
            color: "from-blue-500 to-cyan-400"
        },
        {
            title: "AI Analysis",
            desc: "Powered by advanced NLP, DSuite identifies technical dependencies, risks, and contradictory requirements instantly.",
            icon: <Cpu className="h-16 w-16 text-indigo-500" />,
            color: "from-indigo-500 to-purple-400"
        },
        {
            title: "Visual Roadmap",
            desc: "Watch your static document transform into an interactive 3D roadmap and precise architecture diagrams.",
            icon: <Layout className="h-16 w-16 text-pink-500" />,
            color: "from-pink-500 to-rose-400"
        },
        {
            title: "Ready to Build",
            desc: "Export Jira tickets, GitHub issues, or download scaffolding code straight to your local environment.",
            icon: <Code className="h-16 w-16 text-green-500" />,
            color: "from-green-500 to-emerald-400"
        }
    ];

    useEffect(() => {
        const ctx = gsap.context(() => {
            const panels = gsap.utils.toArray('.panel-3d');

            const tl = gsap.timeline({
                scrollTrigger: {
                    trigger: wrapperRef.current,
                    pin: true,
                    start: "top top",
                    end: `+=${panels.length * 100}%`,
                    scrub: 1,
                }
            });

            gsap.set(panels, {
                z: i => i === 0 ? 0 : -2000,
                autoAlpha: i => i === 0 ? 1 : 0,
                rotationX: i => i === 0 ? 0 : 45,
                scale: i => i === 0 ? 1 : 0.4
            });

            panels.forEach((panel, i) => {
                if (i < panels.length - 1) {
                    const nextPanel = panels[i + 1];

                    tl.to(panel, {
                        z: 1500,
                        autoAlpha: 0,
                        scale: 1.5,
                        rotationX: -45,
                        duration: 1,
                        ease: "power1.inOut"
                    }, i);

                    tl.to(nextPanel, {
                        z: 0,
                        autoAlpha: 1,
                        scale: 1,
                        rotationX: 0,
                        duration: 1,
                        ease: "power1.inOut"
                    }, i);
                }
            });

            gsap.to('.float-shape', {
                y: "-=15",
                duration: 2.5,
                repeat: -1,
                yoyo: true,
                ease: "sine.inOut",
                stagger: {
                    amount: 1.5,
                    from: "random"
                }
            });

        }, wrapperRef);
        return () => ctx.revert();
    }, []);

    return (
        <div ref={wrapperRef} className="relative w-full h-screen overflow-hidden bg-app-bg-page border-y border-app-border-light" style={{ perspective: "1200px" }}>
            {/* Background Atmosphere */}
            <div className="absolute inset-0 z-0 opacity-20 bg-[linear-gradient(rgba(255,255,255,.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.05)_1px,transparent_1px)] bg-[size:50px_50px] [transform:rotateX(60deg)_translateY(-100px)_translateZ(-200px)] pointer-events-none"></div>

            <div className="absolute inset-0 z-0 flex items-center justify-center pointer-events-none">
                <div className="w-[600px] h-[600px] bg-blue-500/5 rounded-full absolute mix-blend-screen" style={{ transform: "translateZ(0)" }}></div>
                <div className="w-[500px] h-[500px] bg-indigo-500/5 rounded-full absolute mix-blend-screen -mt-40" style={{ transform: "translateZ(0)" }}></div>
            </div>

            {/* Panels Container */}
            <div className="absolute inset-0 flex flex-col items-center justify-center" style={{ transformStyle: "preserve-3d" }}>
                {steps.map((step, i) => (
                    <div
                        key={i}
                        className="panel-3d absolute w-full max-w-6xl px-6 sm:px-12 flex flex-col md:flex-row items-center gap-12 lg:gap-24"
                        style={{ transformStyle: "preserve-3d", willChange: "transform, opacity" }}
                    >
                        {/* 3D Visual Object */}
                        <div className="flex-1 w-full flex justify-center" style={{ perspective: "1000px" }}>
                            <div className="relative w-72 h-72 sm:w-96 sm:h-96 float-shape shadow-xl" style={{ transformStyle: "preserve-3d", willChange: "transform" }}>
                                <div className={`absolute inset-0 rounded-[2rem] bg-gradient-to-br ${step.color} opacity-20`} style={{ transform: 'translateZ(-48px)' }}></div>
                                <div className="absolute inset-0 rounded-[2rem] bg-app-bg-card/95 border border-white/10 shadow-xl flex items-center justify-center" style={{ transformStyle: "preserve-3d" }}>
                                    <div className={`absolute inset-0 bg-gradient-to-br ${step.color} opacity-10 rounded-[2rem]`}></div>
                                    <div className="float-shape shadow-lg bg-white/5 p-8 rounded-3xl border border-white/10" style={{ willChange: "transform" }}>
                                        {step.icon}
                                    </div>
                                    {/* Decorative 3D elements */}
                                    <div className="float-shape absolute top-6 left-6 w-16 h-16 rounded-2xl bg-gradient-to-tr from-white/10 to-transparent border border-white/10" style={{ transform: 'translateZ(-40px) translateX(20px)', willChange: "transform" }}></div>
                                    <div className="float-shape absolute bottom-8 right-8 w-20 h-20 rounded-full bg-gradient-to-bl from-white/10 to-transparent border border-white/10" style={{ transform: 'translateZ(50px) translateY(-20px)', willChange: "transform" }}></div>
                                    <div className="float-shape absolute top-1/2 -right-12 w-12 h-12 rounded-lg bg-gradient-to-br from-white/10 to-transparent border border-white/10" style={{ transform: 'translateZ(20px) rotate(45deg)', willChange: "transform" }}></div>
                                </div>
                            </div>
                        </div>

                        {/* Text Content */}
                        <div className="flex-1 space-y-6 text-center md:text-left z-10 bg-app-bg-page/50 md:bg-transparent p-6 rounded-3xl backdrop-blur-sm md:backdrop-blur-none" style={{ transform: 'translateZ(50px)' }}>
                            <div className="inline-flex items-center gap-2 px-4 py-2 bg-app-bg-hover rounded-full border border-app-border text-app-text-main text-sm font-bold tracking-widest shadow-sm">
                                <span>STEP 0{i + 1}</span>
                                <div className={`h-2.5 w-2.5 rounded-full bg-gradient-to-r ${step.color} shadow-[0_0_10px_rgba(255,255,255,0.5)]`}></div>
                            </div>
                            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-white tracking-tight leading-tight drop-shadow-lg">
                                {step.title}
                            </h2>
                            <p className="text-xl sm:text-2xl text-app-text-label leading-relaxed drop-shadow-md font-light">
                                {step.desc}
                            </p>
                        </div>
                    </div>
                ))}
            </div>

            {/* Scroll Indicator */}
            <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 opacity-70 animate-bounce">
                <span className="text-xs uppercase tracking-widest text-app-text-label font-semibold">Scroll</span>
                <div className="w-5 h-8 rounded-full border-2 border-app-text-label flex justify-center pt-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-app-text-label"></div>
                </div>
            </div>
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
        <div className="min-h-screen text-app-text-main font-sans overflow-x-hidden relative">
            <BackgroundMarquee />

            {/* Navigation */}
            <nav className="fixed w-full bg-app-bg-card/95 z-50 border-b border-app-border-light transition-all duration-300" style={{ transform: "translateZ(0)" }}>
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex justify-between items-center h-16">
                        <div className="flex items-center gap-3">
                            <img src={Logo} alt="DSuite" className="h-10 w-auto" />
                            <div className="h-6 w-px bg-app-bg-hover"></div>
                            <span className="text-xl font-bold tracking-tight text-app-text-main">DSuite</span>
                        </div>
                        <div className="flex items-center gap-4">
                            <button
                                onClick={openLogin}
                                className="text-app-text-label hover:text-app-text-main font-medium transition-colors cursor-pointer bg-transparent border-0"
                            >
                                Log in
                            </button>
                            <button
                                onClick={openSignup}
                                className="hidden sm:inline-flex bg-app-primary hover:bg-app-primary-hover text-white px-5 py-2.5 rounded-lg font-semibold transition-transform hover:scale-105 shadow-md shadow-blue-500/20 cursor-pointer border-0"
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
                        <div className="inline-flex items-center gap-2 px-3 py-1 bg-app-primary-light border border-app-primary-light rounded-full text-app-primary text-xs font-semibold mx-auto lg:mx-0">
                            <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                            </span>
                            AI-Powered Analysis v1.0
                        </div>
                        <h1 className="text-4xl sm:text-5xl lg:text-7xl font-extrabold tracking-tight leading-tight text-app-text-main">
                            Transform <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600">Docs</span> into Intelligence
                        </h1>
                        <p className="text-lg sm:text-xl text-app-text-label leading-relaxed max-w-lg mx-auto lg:mx-0">
                            Instantly analyze Business Requirement Documents (BRDs) with advanced AI. Get feasibility checks and technical insights in seconds.
                        </p>
                        <div className="flex flex-col sm:flex-row gap-4 pt-4 justify-center lg:justify-start">
                            <button
                                onClick={openSignup}
                                className="inline-flex justify-center items-center px-8 py-4 text-base font-bold text-white bg-app-primary rounded-xl hover:bg-app-primary-hover transition-all shadow-lg hover:shadow-xl hover:-translate-y-0.5 active:translate-y-0 cursor-pointer border-0"
                            >
                                Start Analysis Free
                                <ArrowRight className="ml-2 h-5 w-5" />
                            </button>
                            <Link
                                to="/how-it-works"
                                className="inline-flex justify-center items-center px-8 py-4 text-base font-bold text-app-text-label bg-app-bg-card border border-app-border rounded-xl hover:bg-app-bg-page transition-colors"
                            >
                                How it works
                            </Link>
                        </div>
                        <div className="flex flex-wrap justify-center lg:justify-start gap-4 pt-4 text-sm text-app-text-muted">
                            <div className="flex items-center gap-1">
                                <CheckCircle className="h-4 w-4 text-app-status-success shrink-0" />
                                <span>No credit card required</span>
                            </div>
                            <div className="flex items-center gap-1">
                                <CheckCircle className="h-4 w-4 text-app-status-success shrink-0" />
                                <span>Enterprise-grade security</span>
                            </div>
                        </div>
                    </div>

                    <div className="hero-image relative mt-8 lg:mt-0 w-full">
                        <div className="absolute -inset-4 bg-gradient-to-r from-blue-500/20 to-indigo-500/20 rounded-full blur-3xl opacity-50"></div>
                        <HeroInteractiveImage />
                    </div>
                </div>
            </section>

            {/* Interactive 3D Scroll Section */}
            <Interactive3DScroll />

            {/* Features Section */}
            <section id="features" ref={featuresRef} className="py-10 bg-app-bg-card/90 relative z-10 border-t border-app-border-light" style={{ transform: "translateZ(0)" }}>
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="text-center max-w-3xl mx-auto mb-12">
                        <h2 className="text-3xl font-bold tracking-tight text-app-text-main sm:text-4xl mb-4">
                            Everything you need
                        </h2>
                        <p className="text-lg text-app-text-label">
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
                            <div key={idx} className="feature-card bg-app-bg-card p-6 rounded-2xl shadow-sm border border-app-border-light hover:shadow-md transition-shadow">
                                <div className={`h-12 w-12 ${feature.color} rounded-xl flex items-center justify-center mb-4 shadow-md shadow-blue-500/10`}>
                                    {feature.icon}
                                </div>
                                <h3 className="text-lg font-bold text-app-text-main mb-2">{feature.title}</h3>
                                <p className="text-app-text-label text-sm leading-relaxed">
                                    {feature.desc}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA Section */}
            <section className="py-20 px-4 sm:px-6 lg:px-8 relative z-10">
                <div ref={ctaRef} className="max-w-5xl mx-auto bg-app-text-main rounded-3xl overflow-hidden relative shadow-2xl">
                    <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-10 mix-blend-overlay"></div>
                    <div className="absolute -top-24 -right-24 w-96 h-96 bg-app-primary/30 rounded-full blur-3xl"></div>
                    <div className="absolute -bottom-24 -left-24 w-96 h-96 bg-purple-600/30 rounded-full blur-3xl"></div>

                    <div className="relative px-6 py-12 md:px-12 md:py-16 text-center">
                        <h2 className="text-2xl md:text-4xl font-bold text-white mb-4 tracking-tight">
                            Ready to clean up your docs?
                        </h2>
                        <p className="text-app-border text-base md:text-lg max-w-xl mx-auto mb-8">
                            Join thousands of developers using DSuite today.
                        </p>
                        <button
                            onClick={openSignup}
                            className="inline-flex justify-center items-center px-8 py-3.5 text-base font-bold text-app-text-main bg-app-bg-card rounded-xl hover:bg-app-bg-page transition-colors shadow-lg active:scale-95 cursor-pointer border-0"
                        >
                            Get Started for Free
                            <ArrowRight className="ml-2 h-5 w-5" />
                        </button>
                    </div>
                </div>
            </section>

            {/* Footer */}
            <footer className="bg-app-bg-card border-t border-app-border-light py-8 relative z-10">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center text-app-text-light text-sm">
                    <p>© 2026 DSuite. All rights reserved.</p>
                </div>
            </footer>

            {/* Modals */}
            {(isLoginOpen || isSignupOpen) && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
                    <div
                        className="absolute inset-0 bg-app-text-main/40 backdrop-blur-sm transition-opacity opacity-100"
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
