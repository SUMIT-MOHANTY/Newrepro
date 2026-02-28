import { useRef, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import {
    ArrowRight, Zap, CheckCircle, Shield, Workflow,
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
                    className="absolute -right-2 sm:-right-4 bottom-4 sm:bottom-8 w-56 sm:w-64 bg-app-bg-page/95 border border-app-border-light p-4 sm:p-5 rounded-2xl shadow-2xl"
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
            title: "DSuite Master Analysis",
            desc: "Document is uploaded into DSuite. The platform analyzes requirements, validates architecture direction, and prepares an execution-ready blueprint.",
            icon: <FileText className="h-16 w-16 text-blue-500" />,
            color: "from-blue-500 to-cyan-400"
        },
        {
            title: "Nxdune Orchestration",
            desc: "The DSuite blueprint is routed to Nxdune. Nxdune creates the workspace and automatically distributes Dev, Test, and Deploy tasks to agents.",
            icon: <Workflow className="h-16 w-16 text-indigo-500" />,
            color: "from-indigo-500 to-purple-400"
        },
        {
            title: "Dev + Test Agent Execution",
            desc: "Dev Agent works through N-Mod EXT to build the solution. Test Agent runs Kaktox validations and confirms quality before release.",
            icon: <Code className="h-16 w-16 text-pink-500" />,
            color: "from-pink-500 to-rose-400"
        },
        {
            title: "Deploy Agent -> CloudSpx",
            desc: "After approval, Deploy Agent pushes the validated build through CloudSpx pipelines while execution traceability stays visible in Nxdune.",
            icon: <Server className="h-16 w-16 text-green-500" />,
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
                    end: `+=${panels.length * 70}%`,
                    scrub: 0.35,
                }
            });

            gsap.set(panels, {
                z: i => i === 0 ? 0 : -1200,
                autoAlpha: i => i === 0 ? 1 : 0,
                rotationX: i => i === 0 ? 0 : 24,
                scale: i => i === 0 ? 1 : 0.72
            });

            panels.forEach((panel, i) => {
                if (i < panels.length - 1) {
                    const nextPanel = panels[i + 1];

                    tl.to(panel, {
                        z: 900,
                        autoAlpha: 0,
                        scale: 1.18,
                        rotationX: -20,
                        duration: 0.65,
                        ease: "power1.out"
                    }, i);

                    tl.to(nextPanel, {
                        z: 0,
                        autoAlpha: 1,
                        scale: 1,
                        rotationX: 0,
                        duration: 0.65,
                        ease: "power1.out"
                    }, i);
                }
            });

            gsap.to('.float-shape', {
                y: "-=8",
                duration: 1.8,
                repeat: -1,
                yoyo: true,
                ease: "sine.inOut",
                stagger: {
                    amount: 0.8,
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
                        <div className="flex-1 space-y-6 text-center md:text-left z-10 bg-app-bg-page/50 md:bg-transparent p-6 rounded-3xl" style={{ transform: 'translateZ(50px)' }}>
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

const EfficiencySection = () => {
    return (
        <section className="py-20 relative z-10 bg-app-bg-page overflow-hidden border-t border-app-border-light">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(56,189,248,0.05)_0%,_transparent_70%)] pointer-events-none" />
            <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 relative">
                <div className="flex flex-col lg:flex-row items-center gap-8 lg:gap-14">
                    <div className="flex-1 space-y-6">
                        <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded-full text-blue-600 text-xs font-bold tracking-widest uppercase">
                            <Zap className="h-3.5 w-3.5" />
                            Pre-IDE Acceleration
                        </div>
                        <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-app-text-main leading-tight">
                            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600 shrink-0">80% of the work.</span><br />
                            Done before you even open your IDE.
                        </h2>
                        <p className="text-lg text-app-text-label leading-relaxed">
                            Stop wasting engineering hours on boilerplate, initial scaffolding, and basic architectural setups.
                            DSuite Agents handle the heavy lifting straight from your requirements.
                        </p>
                        <div className="space-y-3">
                            {[
                                { title: 'Architecture & DB Schema Generation', icon: <Database className="w-4 h-4" /> },
                                { title: 'API scaffolding & Routing', icon: <Server className="w-4 h-4" /> },
                                { title: 'Base UI components setup', icon: <Layout className="w-4 h-4" /> },
                            ].map((item, idx) => (
                                <div key={idx} className="flex items-center gap-3 bg-app-bg-card p-3 rounded-2xl border border-app-border-light shadow-sm">
                                    <div className="h-8 w-8 bg-blue-50 rounded-xl flex items-center justify-center text-blue-600 shrink-0">
                                        {item.icon}
                                    </div>
                                    <span className="font-semibold text-app-text-main text-base">{item.title}</span>
                                    <CheckCircle className="w-5 h-5 text-green-500 ml-auto" />
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="flex-1 w-full relative">
                        <div className="relative bg-app-bg-card rounded-[2rem] border border-app-border-light shadow-2xl p-6 sm:p-8 flex flex-col justify-center overflow-hidden">
                            <div className="absolute top-0 right-0 w-56 h-56 bg-blue-400/20 rounded-full blur-[80px]" />
                            <div className="absolute bottom-0 left-0 w-56 h-56 bg-indigo-400/20 rounded-full blur-[80px]" />

                            <h3 className="text-xl font-bold text-app-text-main mb-8 text-center relative z-10">Traditional vs Agentic Workflow</h3>

                            <div className="space-y-6 relative z-10 w-full max-w-sm mx-auto">
                                {/* Traditional */}
                                <div>
                                    <div className="flex justify-between text-xs font-semibold mb-2">
                                        <span className="text-app-text-muted">Human Effort</span>
                                        <span className="text-app-text-muted">100% Manual</span>
                                    </div>
                                    <div className="h-3 w-full bg-slate-100 rounded-full overflow-hidden flex border border-slate-200">
                                        <div className="h-full bg-slate-300 w-[10%]"></div>
                                        <div className="h-full bg-slate-400 w-[80%]"></div>
                                        <div className="h-full bg-slate-500 w-[10%]"></div>
                                    </div>
                                    <div className="flex text-[9px] sm:text-[10px] font-bold text-app-text-muted mt-2 uppercase tracking-wide">
                                        <span className="w-[10%] text-center">Plan</span>
                                        <span className="w-[80%] text-center">Manual Coding</span>
                                        <span className="w-[10%] text-center">Deploy</span>
                                    </div>
                                </div>

                                {/* Agentic */}
                                <div className="p-4 bg-blue-50/50 rounded-2xl border border-blue-100/50 mt-6">
                                    <div className="flex justify-between text-xs font-semibold mb-2">
                                        <span className="text-app-text-main">With DSuite Agents</span>
                                        <span className="text-blue-600">80% Automated</span>
                                    </div>
                                    <div className="h-8 w-full bg-app-bg-page rounded-xl overflow-hidden flex shadow-inner border border-app-border">
                                        <div className="h-full bg-gradient-to-r from-indigo-500 to-blue-500 w-[80%] flex items-center justify-center relative shadow-[inset_0_2px_10px_rgba(0,0,0,0.1)]">
                                            <div className="absolute inset-0 opacity-20 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCI+CjxyZWN0IHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCIgZmlsbD0ibm9uZSIvPgo8bGluZSB4MT0iMCIgeTE9IjIwIiB4Mj0iMjAiIHkyPSIwIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjUiLz4KPC9zdmc+')]"></div>
                                            <span className="text-[10px] sm:text-xs font-bold text-white relative z-10 flex items-center gap-1.5 drop-shadow-md">
                                                <Zap className="w-3.5 h-3.5 fill-white" />
                                                80% Agentic Pre-Work
                                            </span>
                                        </div>
                                        <div className="h-full bg-white w-[20%] flex items-center justify-center border-l-2 border-blue-400">
                                            <span className="text-[9px] sm:text-[10px] font-bold text-blue-600">20% IDE</span>
                                        </div>
                                    </div>
                                    <div className="flex justify-between mt-2 text-[10px]">
                                        <span className="text-indigo-600 font-bold max-w-[70%] text-left leading-tight">Scaffold, APIs, UI, Schemas, Tests, Deploy</span>
                                        <span className="text-blue-600 font-bold flex-1 text-right">Human Polish</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
};

const LandingPage = () => {
    const heroRef = useRef(null);
    const ctaRef = useRef(null);
    const [isLoginOpen, setIsLoginOpen] = useState(false);
    const [isSignupOpen, setIsSignupOpen] = useState(false);
    const [activeModeKey, setActiveModeKey] = useState('developer');

    const projectUseCases = [
        {
            key: 'greenfield',
            title: 'Greenfield Development',
            subtitle: 'Build from scratch',
            icon: <Zap className="h-5 w-5 text-white" />,
            color: 'bg-emerald-500',
            ring: 'border-emerald-200',
            bg: 'bg-emerald-50/70',
            useCase: [
                'No existing system or legacy constraints',
                'New architecture and new tech stack',
                'Complete freedom in design and implementation',
                'Example: Building a new SaaS product from zero'
            ],
            solution: [
                'DSuite extracts architecture-ready requirements from BRD',
                'Defines module boundaries and implementation flow early',
                'Generates a build-ready roadmap before coding starts'
            ],
            comparison: {
                existing: 'No',
                freedom: 'High',
                risk: 'Medium',
                typical: 'New product'
            }
        },
        {
            key: 'brownfield',
            title: 'Brownfield Development',
            subtitle: 'Enhancement of existing systems',
            icon: <Workflow className="h-5 w-5 text-white" />,
            color: 'bg-amber-600',
            ring: 'border-amber-200',
            bg: 'bg-amber-50/70',
            useCase: [
                'Existing application already in place',
                'Adds features, integrations, or modules',
                'Works within current architecture and constraints',
                'May require selective refactoring'
            ],
            solution: [
                'Maps new requirements against current system boundaries',
                'Flags integration risks and dependency impacts upfront',
                'Prioritizes change-safe rollout plans and task sequencing'
            ],
            note: 'Most enterprise projects fall into this category.',
            comparison: {
                existing: 'Yes',
                freedom: 'Limited',
                risk: 'Medium-High',
                typical: 'Feature enhancements'
            }
        },
        {
            key: 'modernization',
            title: 'Modernization / Re-engineering',
            subtitle: 'Legacy transformation',
            icon: <Cpu className="h-5 w-5 text-white" />,
            color: 'bg-sky-600',
            ring: 'border-sky-200',
            bg: 'bg-sky-50/70',
            useCase: [
                'Rebuild or significantly transform legacy applications',
                'Technology migration, architecture migration, and cloud migration',
                'UI modernization from legacy desktop to modern web',
                'Focus on scalability, maintainability, and performance'
            ],
            solution: [
                'Supports phased strategies: rehost, replatform, refactor, rebuild, replace',
                'Builds migration-ready dependency and risk views from BRD inputs',
                'Creates execution plans aligned to modernization milestones'
            ],
            comparison: {
                existing: 'Yes (Legacy)',
                freedom: 'Partial',
                risk: 'High',
                typical: 'Digital transformation'
            }
        }
    ];

    const platformModes = [
        {
            key: 'developer',
            title: 'Developer Mode',
            subtitle: 'Human-Led Development',
            icon: <Code className="h-5 w-5 text-white" />,
            color: 'from-blue-600 to-cyan-500',
            description: 'In this model, all work is performed manually by developers. AI is only used as a reference tool.',
            brief: 'Teams follow a fully human-led delivery path where architecture decisions, coding standards, and validation gates are handled directly by engineers. This model minimizes automation risk and gives leadership complete visibility into every change before release. It is effective when accuracy, accountability, and auditability are more important than delivery speed.',
            executiveView: [
                'Maximum human control',
                'Lower automation',
                'Slower but highly controlled execution',
                'Suitable for sensitive or regulated environments'
            ],
            bestForPoints: [
                'Mission-critical systems',
                'Compliance-heavy industries',
                'Deep innovation work'
            ]
        },
        {
            key: 'auto-complete',
            title: 'Auto-Complete Mode',
            subtitle: 'AI-Assisted Productivity',
            icon: <Terminal className="h-5 w-5 text-white" />,
            color: 'from-indigo-600 to-violet-500',
            description: 'AI acts as a smart assistant, suggesting improvements and accelerating routine tasks while humans remain in full control.',
            brief: 'This mode improves day-to-day engineering throughput by automating routine drafting, code suggestions, and repetitive refinement work. Developers still make final decisions and keep ownership of quality, security, and release readiness. It provides quick productivity gains without requiring major process or governance changes.',
            executiveView: [
                'Improves productivity without reducing oversight',
                'Low risk',
                'Quick return on investment',
                'Minimal process disruption'
            ],
            bestForPoints: [
                'Organizations seeking incremental productivity gains',
                'Teams that want minimal process disruption',
                'Enterprises avoiding structural change in delivery'
            ]
        },
        {
            key: 'vibe',
            title: 'Vibe Coding Mode',
            subtitle: 'Intent-Driven Development',
            icon: <FileCode className="h-5 w-5 text-white" />,
            color: 'from-fuchsia-600 to-pink-500',
            description: 'Teams describe desired outcomes, and AI generates structured outputs rapidly. Humans refine and validate.',
            brief: 'Vibe Coding is intent-first: teams define business outcomes and AI translates them into draft implementation paths quickly. This allows rapid concept testing, faster prototyping cycles, and accelerated early-stage feature development. Human review remains essential to align outputs with architecture standards and governance expectations.',
            executiveView: [
                'Rapid prototyping',
                'Faster product launches',
                'Encourages experimentation',
                'Requires governance oversight'
            ],
            bestForPoints: [
                'Innovation labs',
                'MVP delivery',
                'Digital product acceleration'
            ]
        },
        {
            key: 'coexistence',
            title: 'Co-Existence Mode',
            subtitle: 'Human + AI Collaboration Model',
            icon: <CheckCircle className="h-5 w-5 text-white" />,
            color: 'from-emerald-600 to-teal-500',
            description: 'Humans and AI actively collaborate. AI handles repetitive and analytical tasks while humans focus on strategy, architecture, and decision-making.',
            brief: 'Co-Existence combines human judgment with AI execution in a shared workflow. AI accelerates analysis, drafting, and repetitive implementation tasks while people guide architecture, prioritization, and final sign-off decisions. This balance supports sustainable scale in enterprise engineering without sacrificing control or quality.',
            executiveView: [
                'Balanced automation',
                'Higher productivity',
                'Preserves strategic human oversight',
                'Sustainable long-term model'
            ],
            bestForPoints: [
                'Scaling technology organizations',
                'Programs requiring both speed and control',
                'Quality-focused multi-team engineering'
            ],
            note: 'This is currently the most practical enterprise model.'
        },
        {
            key: 'sandbox',
            title: 'Sandbox Mode',
            subtitle: 'Fully Autonomous AI Environment',
            icon: <Shield className="h-5 w-5 text-white" />,
            color: 'from-sky-600 to-cyan-500',
            description: 'AI independently builds, tests, and iterates with minimal human involvement.',
            brief: 'Sandbox mode runs autonomous AI workflows inside a separate, isolated environment to reduce impact on core systems. It enables rapid experimentation, repeated test cycles, and controlled iteration at high speed. This is suited for internal innovation tracks where strong monitoring and clear boundaries are already in place.',
            executiveView: [
                'Maximum speed',
                'High experimentation potential',
                'Elevated risk without guardrails',
                'Requires strong monitoring systems'
            ],
            bestForPoints: [
                'Internal tools',
                'R&D environments',
                'Innovation pilots'
            ]
        }
    ];

    const activeMode = platformModes.find((mode) => mode.key === activeModeKey) || platformModes[0];
    const modeRoleBlueprints = {
        developer: [
            {
                role: 'Project Lead',
                persona: 'Tech Lead, Senior Developer, or Engineering Manager',
                icon: <Workflow className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Breaks tickets into manual implementation plans',
                    'Reviews design and architecture decisions before coding',
                    'Coordinates handoffs and review milestones'
                ],
                authority: 'Final technical approval before implementation',
                mapsTo: 'Tech Lead, Scrum Master (technical), Senior Engineer'
            },
            {
                role: 'Developers',
                persona: 'Individual Contributors',
                icon: <Code className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Implement code manually and validate correctness',
                    'Own quality, edge-case handling, and optimization',
                    'Write and execute tests, then deploy'
                ],
                authority: 'Approve/reject implementation quality',
                mapsTo: 'Software Engineers (all levels)'
            },
            {
                role: 'Product Manager (Optional)',
                persona: 'Recommended for complex features',
                icon: <FileText className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Validates implementation against business requirements',
                    'Ensures acceptance criteria are testable and complete',
                    'Confirms scope before release'
                ],
                authority: 'Business logic approval before release',
                mapsTo: 'Product Owner or Product Manager'
            }
        ],
        'auto-complete': [
            {
                role: 'Project Lead',
                persona: 'Tech Lead, Senior Developer, or Engineering Manager',
                icon: <Workflow className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Creates guided prompts from tickets and user stories',
                    'Reviews AI suggestions for architecture fit',
                    'Controls where AI assistance is allowed'
                ],
                authority: 'Final approval on assisted outputs before merge',
                mapsTo: 'Tech Lead, Scrum Master (technical), Senior Engineer'
            },
            {
                role: 'Developers',
                persona: 'Individual Contributors',
                icon: <Code className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Use AI suggestions and manually validate every change',
                    'Handle final refinement and reliability hardening',
                    'Write tests and ship production-ready code'
                ],
                authority: 'Approve/reject AI-assisted code',
                mapsTo: 'Software Engineers (all levels)'
            },
            {
                role: 'Product Manager (Optional)',
                persona: 'Recommended for complex features',
                icon: <FileText className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Checks feature intent against business value',
                    'Validates acceptance criteria in proposed output',
                    'Flags scope drift early'
                ],
                authority: 'Business logic approval before finalization',
                mapsTo: 'Product Owner or Product Manager'
            }
        ],
        vibe: [
            {
                role: 'Project Lead',
                persona: 'Tech Lead, Senior Developer, or Engineering Manager',
                icon: <Workflow className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Creates outcome-focused prompts from tickets and stories',
                    'Reviews generated AAPs for technical accuracy',
                    'Coordinates generation rounds and handoffs'
                ],
                authority: 'Final approval on AAP before code generation',
                mapsTo: 'Tech Lead, Scrum Master (technical), Senior Engineer'
            },
            {
                role: 'Developers',
                persona: 'Individual Contributors',
                icon: <Code className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Review generated code for quality and correctness',
                    'Handle final 20% refinement (edge cases, optimizations)',
                    'Write additional tests and deploy'
                ],
                authority: 'Approve/reject generated code and request regeneration',
                mapsTo: 'Software Engineers (all levels)'
            },
            {
                role: 'Product Manager (Optional)',
                persona: 'Recommended for complex features',
                icon: <FileText className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Validates that AAPs align with business requirements',
                    'Ensures acceptance criteria are met in the plan',
                    'Confirms outcome quality before execution'
                ],
                authority: 'Business logic approval before code generation',
                mapsTo: 'Product Owner or Product Manager'
            }
        ],
        coexistence: [
            {
                role: 'Project Lead',
                persona: 'Tech Lead, Senior Developer, or Engineering Manager',
                icon: <Workflow className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Creates prompts from tickets and user stories',
                    'Reviews and approves AAPs for technical accuracy',
                    'Coordinates the generation process and handoffs'
                ],
                authority: 'Final approval on AAP before code generation',
                mapsTo: 'Tech Lead, Scrum Master (technical), Senior Engineer'
            },
            {
                role: 'Developers',
                persona: 'Individual Contributors',
                icon: <Code className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Review generated code for quality and correctness',
                    'Handle final 20% refinement (edge cases, optimizations)',
                    'Write additional tests as needed and deploy'
                ],
                authority: 'Approve/reject generated code and request regeneration',
                mapsTo: 'Software Engineers (all levels)'
            },
            {
                role: 'Product Manager (Optional)',
                persona: 'Recommended for complex features',
                icon: <FileText className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Validates that AAPs align with business requirements',
                    'Ensures acceptance criteria are met in the plan',
                    'Confirms scope and intent before generation'
                ],
                authority: 'Business logic approval before code generation',
                mapsTo: 'Product Owner or Product Manager'
            }
        ],
        sandbox: [
            {
                role: 'Project Lead',
                persona: 'Tech Lead, Senior Developer, or Engineering Manager',
                icon: <Workflow className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Defines guardrails and boundaries for autonomous runs',
                    'Approves autonomy scope and safety checkpoints',
                    'Reviews experiment outcomes and escalation events'
                ],
                authority: 'Controls autonomy level and production promotion',
                mapsTo: 'Tech Lead, Engineering Manager'
            },
            {
                role: 'Developers',
                persona: 'Individual Contributors',
                icon: <Code className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Audit AI-generated code and test artifacts',
                    'Fix reliability/security issues before promotion',
                    'Own production deployment decisions'
                ],
                authority: 'Approve/reject sandbox output for production',
                mapsTo: 'Software Engineers (all levels)'
            },
            {
                role: 'Product Manager (Optional)',
                persona: 'Recommended for complex features',
                icon: <FileText className="h-4 w-4 text-white" />,
                responsibilities: [
                    'Checks feature fit against roadmap priorities',
                    'Validates expected user value from generated output',
                    'Approves experiment-to-product transitions'
                ],
                authority: 'Business approval before production rollout',
                mapsTo: 'Product Owner or Product Manager'
            }
        ],
    };
    const activeModeRoles = modeRoleBlueprints[activeMode.key] || modeRoleBlueprints.coexistence;
    const toSentence = (items = []) => {
        if (items.length === 0) return '';
        if (items.length === 1) return items[0];
        if (items.length === 2) return `${items[0]} and ${items[1]}`;
        return `${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]}`;
    };

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
            <section ref={heroRef} className="pt-24 pb-6 lg:pt-32 lg:pb-12 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto relative z-10">
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
                            Transform <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600">Ideas</span> with Intelligence
                        </h1>
                        <p className="text-lg sm:text-xl text-app-text-label leading-relaxed max-w-lg mx-auto lg:mx-0">
                            Instantly analyze concepts, ideas, and Business Requirement Documents (BRDs) with advanced AI. Get feasibility checks and technical blueprints in seconds.
                        </p>
                        <div className="flex flex-col sm:flex-row gap-4 pt-4 justify-center lg:justify-start">
                            <button
                                onClick={openSignup}
                                className="inline-flex justify-center items-center px-8 py-4 text-base font-bold text-white bg-app-primary rounded-xl hover:bg-app-primary-hover transition-all shadow-lg hover:shadow-xl hover:-translate-y-0.5 active:translate-y-0 cursor-pointer border-0"
                            >
                                Start Analysis
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
                                <span>Professional-grade analysis</span>
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

            {/* Performance/Efficiency Section */}
            <EfficiencySection />

            {/* Interactive 3D Scroll Section */}
            <Interactive3DScroll />

            {/* Use Cases Section */}
            <section className="py-14 bg-app-bg-page/90 relative z-10 border-t border-app-border-light">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="text-center max-w-4xl mx-auto mb-10">
                        <h2 className="text-3xl font-bold tracking-tight text-app-text-main sm:text-4xl mb-4">
                            Enterprise Project Use Cases and Our Solution
                        </h2>
                        <p className="text-lg text-app-text-label">
                            In application development, projects are typically categorized as Greenfield, Brownfield, or Modernization.
                            This is the standard classification used in enterprise documentation, proposals, and RFP responses.
                        </p>
                    </div>

                    <div className="grid lg:grid-cols-3 gap-6">
                        {projectUseCases.map((item) => (
                            <article key={item.key} className={`rounded-2xl border ${item.ring} bg-app-bg-card shadow-sm overflow-hidden`}>
                                <div className={`px-5 py-4 border-b border-app-border-light ${item.bg}`}>
                                    <div className="flex items-center gap-3">
                                        <div className={`h-10 w-10 ${item.color} rounded-xl flex items-center justify-center shadow-sm`}>
                                            {item.icon}
                                        </div>
                                        <div>
                                            <h3 className="text-lg font-bold text-app-text-main">{item.title}</h3>
                                            <p className="text-sm text-app-text-label">{item.subtitle}</p>
                                        </div>
                                    </div>
                                </div>

                                <div className="p-5 space-y-5">
                                    <div>
                                        <p className="text-xs font-bold tracking-widest uppercase text-app-text-light mb-3">Use Case</p>
                                        <ul className="space-y-2">
                                            {item.useCase.map((point, idx) => (
                                                <li key={idx} className="flex items-start gap-2 text-sm text-app-text-label leading-relaxed">
                                                    <CheckCircle className="h-4 w-4 text-app-status-success mt-0.5 shrink-0" />
                                                    <span>{point}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>

                                    <div className="rounded-xl border border-app-border bg-app-bg-page p-4">
                                        <p className="text-xs font-bold tracking-widest uppercase text-app-text-light mb-3">Our Solution</p>
                                        <ul className="space-y-2">
                                            {item.solution.map((point, idx) => (
                                                <li key={idx} className="flex items-start gap-2 text-sm text-app-text-label leading-relaxed">
                                                    <ArrowRight className="h-4 w-4 text-app-primary mt-0.5 shrink-0" />
                                                    <span>{point}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>

                                    {item.note && (
                                        <p className="text-sm font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                                            {item.note}
                                        </p>
                                    )}
                                </div>
                            </article>
                        ))}
                    </div>

                </div>
            </section>

            {/* Working Modes Section */}
            <section className="py-14 bg-app-bg-card/90 relative z-10 border-t border-app-border-light">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="text-center max-w-4xl mx-auto mb-10">
                        <h2 className="text-3xl font-bold tracking-tight text-app-text-main sm:text-4xl mb-4">
                            AI Collaboration Models in Software Development
                        </h2>
                        <p className="text-lg text-app-text-label">
                            Executive Overview: As organizations adopt AI in engineering, each operating model balances control, speed, risk, and automation differently.
                        </p>
                    </div>

                    <div className="grid md:grid-cols-[280px_1fr] lg:grid-cols-[320px_1fr] gap-6 items-stretch">
                        <div className="rounded-2xl border border-app-border-light bg-app-bg-card overflow-hidden shadow-sm h-full">
                            {platformModes.map((mode, idx) => {
                                const isActive = mode.key === activeMode.key;
                                const isLast = idx === platformModes.length - 1;

                                return (
                                    <button
                                        key={mode.key}
                                        type="button"
                                        onClick={() => setActiveModeKey(mode.key)}
                                        aria-pressed={isActive}
                                        className={`w-full text-left px-5 py-4 transition-colors ${isLast ? '' : 'border-b border-app-border-light'} ${isActive ? 'bg-app-bg-page border-l-4 border-l-app-primary pl-4' : 'hover:bg-app-bg-page/70'}`}
                                    >
                                        <div className="flex items-center justify-between gap-3">
                                            <div>
                                                <p className={`font-semibold ${isActive ? 'text-app-text-main' : 'text-app-text-label'}`}>{mode.title}</p>
                                                <p className="text-xs text-app-text-light mt-1">{mode.subtitle}</p>
                                            </div>
                                            <div className={`h-8 w-8 rounded-lg bg-gradient-to-br ${mode.color} flex items-center justify-center shrink-0 shadow-sm`}>
                                                {mode.icon}
                                            </div>
                                        </div>
                                    </button>
                                );
                            })}
                        </div>

                        <article className="rounded-2xl border border-app-border-light bg-app-bg-card shadow-sm p-6 lg:p-7 h-full flex flex-col">
                            <div className="flex flex-wrap items-center gap-4 mb-4">
                                <div className={`h-11 w-11 rounded-xl bg-gradient-to-br ${activeMode.color} flex items-center justify-center shadow-md`}>
                                    {activeMode.icon}
                                </div>
                                <div>
                                    <h3 className="text-2xl font-bold text-app-text-main">{activeMode.title}</h3>
                                    <p className="text-sm text-app-text-light">{activeMode.subtitle}</p>
                                </div>
                            </div>

                            <p className="text-app-text-label leading-relaxed mb-4">
                                {activeMode.description}
                            </p>

                            <div className="rounded-xl border border-app-border bg-app-bg-page p-4 flex-1 flex flex-col justify-between gap-4">
                                <p className="text-sm text-app-text-label leading-relaxed">
                                    {activeMode.brief}
                                </p>
                                <p className="text-sm text-app-text-label leading-relaxed">
                                    <span className="font-semibold text-app-text-main">Executive perspective:</span> {toSentence(activeMode.executiveView)}.
                                </p>
                                <p className="text-sm text-app-text-label leading-relaxed">
                                    <span className="font-semibold text-app-text-main">Where it fits:</span> {toSentence(activeMode.bestForPoints)}.
                                </p>
                                {activeMode.note && (
                                    <p className="text-sm font-semibold text-app-text-main leading-relaxed">
                                        {activeMode.note}
                                    </p>
                                )}
                            </div>
                        </article>
                    </div>

                    <div key={`who-${activeMode.key}`} className="mt-8 rounded-2xl border border-app-border-light bg-app-bg-card shadow-sm p-5 md:p-6 animate-fade-in-up">
                        <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
                            <div>
                                <h3 className="text-2xl font-bold text-app-text-main">Who Does What</h3>
                                <p className="text-sm text-app-text-light mt-1">
                                    During the Blitzy process, roles shift by mode. Current view: <span className="font-semibold text-app-text-main">{activeMode.title}</span>
                                </p>
                            </div>
                            <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold text-white bg-gradient-to-r ${activeMode.color}`}>
                                {activeMode.title}
                            </span>
                        </div>

                        <div className="grid md:grid-cols-3 gap-4">
                            {activeModeRoles.map((item) => (
                                <article
                                    key={`${activeMode.key}-${item.role}`}
                                    className="rounded-xl border border-app-border-light bg-app-bg-page p-4 hover:shadow-md transition-all duration-300 hover:-translate-y-0.5"
                                >
                                    <div className="flex items-start justify-between gap-3 mb-3">
                                        <div>
                                            <h4 className="text-base font-bold text-app-text-main">{item.role}</h4>
                                            <p className="text-xs text-app-text-light mt-0.5">{item.persona}</p>
                                        </div>
                                        <div className={`h-8 w-8 rounded-lg bg-gradient-to-br ${activeMode.color} flex items-center justify-center shrink-0`}>
                                            {item.icon}
                                        </div>
                                    </div>

                                    <p className="text-[10px] font-bold tracking-widest uppercase text-app-text-light mb-2">Responsibilities</p>
                                    <ul className="space-y-1.5 mb-3">
                                        {item.responsibilities.map((point) => (
                                            <li key={point} className="flex items-start gap-2 text-xs text-app-text-label leading-relaxed">
                                                <CheckCircle className="h-3.5 w-3.5 text-app-status-success mt-0.5 shrink-0" />
                                                <span>{point}</span>
                                            </li>
                                        ))}
                                    </ul>

                                    <div className="rounded-lg border border-app-border-light bg-app-bg-card p-2.5 space-y-2">
                                        <p className="text-xs text-app-text-label leading-relaxed">
                                            <span className="font-semibold text-app-text-main">Decision Authority:</span> {item.authority}
                                        </p>
                                        <p className="text-xs text-app-text-label leading-relaxed">
                                            <span className="font-semibold text-app-text-main">Maps to:</span> {item.mapsTo}
                                        </p>
                                    </div>
                                </article>
                            ))}
                        </div>
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
                            Watch the agents work.
                        </h2>
                        <p className="text-app-border text-base md:text-lg max-w-xl mx-auto mb-8">
                            Upload a document into DSuite today and let the ecosystem plan, code, test, and deploy for you.
                        </p>
                        <button
                            onClick={openSignup}
                            className="inline-flex justify-center items-center px-8 py-3.5 text-base font-bold text-app-text-main bg-app-bg-card rounded-xl hover:bg-app-bg-page transition-colors shadow-lg active:scale-95 cursor-pointer border-0"
                        >
                            Get Started
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
