import { ArrowRight, FileText, BrainCircuit, Workflow, Zap, Activity, CheckCircle, Database, Code, Shield, Volume2, VolumeX } from 'lucide-react';
import React, { useRef, useEffect, useLayoutEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import gsap from 'gsap';

import Logo from '../assets/logo.png';
import CloudSpxLogo from '../assets/spx-logo 3.png';
import Logo1 from '../assets/logo1.png';
import KaktoxLogo from '../assets/Kaktox.png';
import NModLogo from '../assets/N-Mod-icon.png';

const AnimatedWorkflowDiagram = () => {
  const containerRef = useRef(null);
  const [currentStepText, setCurrentStepText] = useState("Awaiting Document...");
  const [executionMode, setExecutionMode] = useState("agentic"); // "agentic" | "coexistence"
  const [autonomyMode, setAutonomyMode] = useState("decisive"); // "decisive" | "ask_first"

  useEffect(() => {
    if (!containerRef.current) return;

    const ctx = gsap.context(() => {
      // Clear previous styles/tweens on human elements if context is recreating
      gsap.set([
        '.packet-to-human', '.packet-dev-to-human', '.packet-human-to-nxdune',
        '.path-nxdune-human', '.path-human-nxdune', '.path-dev-human',
        '.packet-to-human-test', '.packet-test-to-human', '.packet-human-test-to-nxdune',
        '.path-nxdune-human-test', '.path-human-test-nxdune', '.path-test-human',
        '.packet-to-human-deploy', '.packet-deploy-to-human', '.packet-human-deploy-to-nxdune',
        '.path-nxdune-human-deploy', '.path-human-deploy-nxdune', '.path-deploy-human'
      ], { opacity: 0 });

      const tl = gsap.timeline({ repeat: -1 });
      const isCoex = executionMode === "coexistence";
      const isAskFirst = autonomyMode === "ask_first";

      if (isCoex || isAskFirst) {
        gsap.set(['.path-nxdune-human', '.path-nxdune-human-test', '.path-nxdune-human-deploy'], { opacity: isCoex ? 1 : 0 });
        gsap.set(['.path-dev-human', '.path-test-human', '.path-deploy-human'], { opacity: isAskFirst ? 1 : 0 });
        gsap.set(['.path-human-nxdune', '.path-human-test-nxdune', '.path-human-deploy-nxdune'], { opacity: (isCoex || isAskFirst) ? 1 : 0 });
      }

      // Step 1: Uploading
      tl.call(() => setCurrentStepText("1. Doc is being uploaded..."))
        .to('.packet-doc', { opacity: 1, duration: 0.2 })
        .to('.packet-doc', { motionPath: { path: '.path-upload', align: '.path-upload', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
        .to('.dsuite-ring', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
        .set('.packet-doc', { opacity: 0 });

      // Step 2: DSuite analyzes
      tl.call(() => setCurrentStepText("2. DSuite Analysis done..."))
        .to('.dsuite-pulse', { opacity: 1, scale: 1.2, duration: 0.5, yoyo: true, repeat: 3 })
        .to({}, { duration: 0.5 })

        // Sending to Nxdune
        .call(() => setCurrentStepText("3. Extracting to Nxdune..."))
        .to('.packet-to-nxdune', { opacity: 1, duration: 0.2 })
        .to('.packet-to-nxdune', { motionPath: { path: '.path-dsuite-nxdune', align: '.path-dsuite-nxdune', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
        .to('.nxdune-ring', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
        .set('.packet-to-nxdune', { opacity: 0 });

      // Step 3: Nxdune processes
      tl.call(() => setCurrentStepText("4. Task created through Nxdune..."))
        .to('.nxdune-pulse', { opacity: 1, scale: 1.2, duration: 0.5, yoyo: true, repeat: 3 })
        .to({}, { duration: 0.5 })

      // Dev Task
      if (isCoex) {
        tl.call(() => setCurrentStepText("5. Co-working: Appointing Dev & Human..."))
          .to(['.packet-to-dev', '.packet-to-human'], { opacity: 1, duration: 0.2 })
          .to('.packet-to-dev', { motionPath: { path: '.path-nxdune-dev', align: '.path-nxdune-dev', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" }, "to-dev")
          .to('.packet-to-human', { motionPath: { path: '.path-nxdune-human', align: '.path-nxdune-human', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" }, "to-dev")
          .to(['.agent-ring-dev', '.human-ring'], { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
          .set(['.packet-to-dev', '.packet-to-human'], { opacity: 0 })

          .call(() => setCurrentStepText("6. Dev Agent & Human working..."))
          .to(['.agent-pulse-dev', '.human-pulse'], { opacity: 1, scale: 1.1, duration: 0.5, yoyo: true, repeat: 3 });
      } else {
        tl.call(() => setCurrentStepText("5. Appointing Dev Task to Dev Agent..."))
          .to('.packet-to-dev', { opacity: 1, duration: 0.2 })
          .to('.packet-to-dev', { motionPath: { path: '.path-nxdune-dev', align: '.path-nxdune-dev', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
          .to('.agent-ring-dev', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
          .set('.packet-to-dev', { opacity: 0 })

          .call(() => setCurrentStepText("6. Dev Agent completing task..."))
          .to('.agent-pulse-dev', { opacity: 1, scale: 1.1, duration: 0.5, yoyo: true, repeat: 3 });
      }

      // Return or Ask First
      if (isAskFirst) {
        tl.call(() => setCurrentStepText("Awaiting Human Approval..."))
          .to('.packet-dev-to-human', { opacity: 1, duration: 0.2 })
          .to('.packet-dev-to-human', { motionPath: { path: '.path-dev-human', align: '.path-dev-human', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
          .set('.packet-dev-to-human', { opacity: 0 })
          .to('.human-pulse', { opacity: 1, scale: 1.1, duration: 0.5, yoyo: true, repeat: 1 })

          .call(() => setCurrentStepText("Action Approved! Returning..."))
          .to('.packet-human-to-nxdune', { opacity: 1, duration: 0.2 })
          .to('.packet-human-to-nxdune', { motionPath: { path: '.path-human-nxdune', align: '.path-human-nxdune', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
          .to('.nxdune-ring', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
          .set('.packet-human-to-nxdune', { opacity: 0 });
      } else {
        if (isCoex) {
          tl.call(() => setCurrentStepText("Co-work done. Returning..."))
            .to(['.packet-return-dev', '.packet-human-to-nxdune'], { opacity: 1, duration: 0.2 })
            .to('.packet-return-dev', { motionPath: { path: '.path-dev-nxdune', align: '.path-dev-nxdune', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" }, "return-dev")
            .to('.packet-human-to-nxdune', { motionPath: { path: '.path-human-nxdune', align: '.path-human-nxdune', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" }, "return-dev")
            .to('.nxdune-ring', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
            .set(['.packet-return-dev', '.packet-human-to-nxdune'], { opacity: 0 });
        } else {
          tl.call(() => setCurrentStepText("Task Done. Returning..."))
            .to('.packet-return-dev', { opacity: 1, duration: 0.2 })
            .to('.packet-return-dev', { motionPath: { path: '.path-dev-nxdune', align: '.path-dev-nxdune', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
            .to('.nxdune-ring', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
            .set('.packet-return-dev', { opacity: 0 });
        }
      }

      // Step 7: Test Task -> Kaktox
      if (isCoex) {
        tl.call(() => setCurrentStepText("7. Co-working QA: Appointing Test & QA Human..."))
          .to(['.packet-to-test', '.packet-to-human-test'], { opacity: 1, duration: 0.2 })
          .to('.packet-to-test', { motionPath: { path: '.path-nxdune-test', align: '.path-nxdune-test', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" }, "to-test")
          .to('.packet-to-human-test', { motionPath: { path: '.path-nxdune-human-test', align: '.path-nxdune-human-test', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" }, "to-test")
          .to(['.agent-ring-test', '.human-qa-ring'], { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
          .set(['.packet-to-test', '.packet-to-human-test'], { opacity: 0 })

          .call(() => setCurrentStepText("8. Test Agent & QA working... Code passes."))
          .to(['.agent-pulse-test', '.human-qa-pulse'], { opacity: 1, scale: 1.1, duration: 0.5, yoyo: true, repeat: 3 });
      } else {
        tl.call(() => setCurrentStepText("7. Appointing Test Task to Test Agent..."))
          .to('.packet-to-test', { opacity: 1, duration: 0.2 })
          .to('.packet-to-test', { motionPath: { path: '.path-nxdune-test', align: '.path-nxdune-test', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
          .to('.agent-ring-test', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
          .set('.packet-to-test', { opacity: 0 })

          // Test Working
          .call(() => setCurrentStepText("8. Test Agent running tests... Code passes."))
          .to('.agent-pulse-test', { opacity: 1, scale: 1.1, duration: 0.5, yoyo: true, repeat: 3 });
      }

      if (isAskFirst) {
        tl.call(() => setCurrentStepText("QA Awaiting Human Approval..."))
          .to('.packet-test-to-human', { opacity: 1, duration: 0.2 })
          .to('.packet-test-to-human', { motionPath: { path: '.path-test-human', align: '.path-test-human', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
          .set('.packet-test-to-human', { opacity: 0 })
          .to('.human-qa-pulse', { opacity: 1, scale: 1.1, duration: 0.5, yoyo: true, repeat: 1 })

          .call(() => setCurrentStepText("QA Action Approved! Returning..."))
          .to('.packet-human-test-to-nxdune', { opacity: 1, duration: 0.2 })
          .to('.packet-human-test-to-nxdune', { motionPath: { path: '.path-human-test-nxdune', align: '.path-human-test-nxdune', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
          .to('.nxdune-ring', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
          .set('.packet-human-test-to-nxdune', { opacity: 0 });
      } else {
        if (isCoex) {
          tl.call(() => setCurrentStepText("Co-work done. Returning..."))
            .to(['.packet-return-test', '.packet-human-test-to-nxdune'], { opacity: 1, duration: 0.2 })
            .to('.packet-return-test', { motionPath: { path: '.path-test-nxdune', align: '.path-test-nxdune', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" }, "return-test")
            .to('.packet-human-test-to-nxdune', { motionPath: { path: '.path-human-test-nxdune', align: '.path-human-test-nxdune', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" }, "return-test")
            .to('.nxdune-ring', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
            .set(['.packet-return-test', '.packet-human-test-to-nxdune'], { opacity: 0 });
        } else {
          tl.call(() => setCurrentStepText("Test Done. Returning..."))
            .to('.packet-return-test', { opacity: 1, duration: 0.2 })
            .to('.packet-return-test', { motionPath: { path: '.path-test-nxdune', align: '.path-test-nxdune', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
            .to('.nxdune-ring', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
            .set('.packet-return-test', { opacity: 0 });
        }
      }

      // Step 9: Deploy Task -> CloudSpx
      if (isCoex) {
        tl.call(() => setCurrentStepText("9. Co-working Deploy: Appointing Deploy & DevOps Human..."))
          .to(['.packet-to-deploy', '.packet-to-human-deploy'], { opacity: 1, duration: 0.2 })
          .to('.packet-to-deploy', { motionPath: { path: '.path-nxdune-deploy', align: '.path-nxdune-deploy', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" }, "to-deploy")
          .to('.packet-to-human-deploy', { motionPath: { path: '.path-nxdune-human-deploy', align: '.path-nxdune-human-deploy', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" }, "to-deploy")
          .to(['.agent-ring-deploy', '.human-deploy-ring'], { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
          .set(['.packet-to-deploy', '.packet-to-human-deploy'], { opacity: 0 })

          .call(() => setCurrentStepText("10. Deploy Agent & DevOps pushing code... Deployed!"))
          .to(['.agent-pulse-deploy', '.human-deploy-pulse'], { opacity: 1, scale: 1.1, duration: 0.5, yoyo: true, repeat: 3 });
      } else {
        tl.call(() => setCurrentStepText("9. Appointing Deploy Task to Deploy Agent..."))
          .to('.packet-to-deploy', { opacity: 1, duration: 0.2 })
          .to('.packet-to-deploy', { motionPath: { path: '.path-nxdune-deploy', align: '.path-nxdune-deploy', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
          .to('.agent-ring-deploy', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
          .set('.packet-to-deploy', { opacity: 0 })

          // Deploy Working
          .call(() => setCurrentStepText("10. Deploy Agent pushing code... Deployed!"))
          .to('.agent-pulse-deploy', { opacity: 1, scale: 1.1, duration: 0.5, yoyo: true, repeat: 3 });
      }

      if (isAskFirst) {
        tl.call(() => setCurrentStepText("Deploy Awaiting Human Approval..."))
          .to('.packet-deploy-to-human', { opacity: 1, duration: 0.2 })
          .to('.packet-deploy-to-human', { motionPath: { path: '.path-deploy-human', align: '.path-deploy-human', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
          .set('.packet-deploy-to-human', { opacity: 0 })
          .to('.human-deploy-pulse', { opacity: 1, scale: 1.1, duration: 0.5, yoyo: true, repeat: 1 })

          .call(() => setCurrentStepText("Deploy Action Approved! Returning..."))
          .to('.packet-human-deploy-to-nxdune', { opacity: 1, duration: 0.2 })
          .to('.packet-human-deploy-to-nxdune', { motionPath: { path: '.path-human-deploy-nxdune', align: '.path-human-deploy-nxdune', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
          .to('.nxdune-ring', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
          .set('.packet-human-deploy-to-nxdune', { opacity: 0 });
      } else {
        if (isCoex) {
          tl.call(() => setCurrentStepText("Co-work done. Returning..."))
            .to(['.packet-return-deploy', '.packet-human-deploy-to-nxdune'], { opacity: 1, duration: 0.2 })
            .to('.packet-return-deploy', { motionPath: { path: '.path-deploy-nxdune', align: '.path-deploy-nxdune', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" }, "return-deploy")
            .to('.packet-human-deploy-to-nxdune', { motionPath: { path: '.path-human-deploy-nxdune', align: '.path-human-deploy-nxdune', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" }, "return-deploy")
            .to('.nxdune-ring', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
            .set(['.packet-return-deploy', '.packet-human-deploy-to-nxdune'], { opacity: 0 });
        } else {
          tl.call(() => setCurrentStepText("Deploy Done. Returning..."))
            .to('.packet-return-deploy', { opacity: 1, duration: 0.2 })
            .to('.packet-return-deploy', { motionPath: { path: '.path-deploy-nxdune', align: '.path-deploy-nxdune', alignOrigin: [0.5, 0.5] }, duration: 1.5, ease: "power1.inOut" })
            .to('.nxdune-ring', { scale: 1.5, opacity: 0, duration: 0.5 }, "-=0.2")
            .set('.packet-return-deploy', { opacity: 0 });
        }
      }

      tl.call(() => setCurrentStepText("Loop completed successfully."))
        .to({}, { duration: 2 }); // Pause before repeat

    }, containerRef);
    return () => ctx.revert();
  }, [executionMode, autonomyMode]);

  return (
    <div className="flex flex-col items-center mt-16 w-full max-w-[1200px] mx-auto">
      {/* Toggles */}
      <div className="flex flex-col sm:flex-row gap-8 mb-4 w-full justify-center opacity-0" style={{ animation: "fadeIn 1s forwards" }}>
        <style dangerouslySetInnerHTML={{
          __html: `
          @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
          }
        `}} />
        <div className="flex flex-col items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Execution Mode</span>
          <div className="flex items-center gap-1 bg-slate-800/80 p-1.5 rounded-full border border-slate-700 shadow-xl backdrop-blur-md">
            <button
              onClick={() => setExecutionMode('agentic')}
              className={`px-5 py-2 rounded-full text-xs font-bold transition-all ${executionMode === 'agentic' ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/30' : 'text-slate-400 hover:text-white hover:bg-slate-700/50'}`}>
              Fully Agentic
            </button>
            <button
              onClick={() => setExecutionMode('coexistence')}
              className={`px-5 py-2 rounded-full text-xs font-bold transition-all ${executionMode === 'coexistence' ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30' : 'text-slate-400 hover:text-white hover:bg-slate-700/50'}`}>
              Coexistence
            </button>
          </div>
        </div>

        <div className="flex flex-col items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Agent Autonomy</span>
          <div className="flex items-center gap-1 bg-slate-800/80 p-1.5 rounded-full border border-slate-700 shadow-xl backdrop-blur-md">
            <button
              onClick={() => setAutonomyMode('decisive')}
              className={`px-5 py-2 rounded-full text-xs font-bold transition-all ${autonomyMode === 'decisive' ? 'bg-emerald-500 text-white shadow-lg shadow-emerald-500/30' : 'text-slate-400 hover:text-white hover:bg-slate-700/50'}`}>
              Decisive
            </button>
            <button
              onClick={() => setAutonomyMode('ask_first')}
              className={`px-5 py-2 rounded-full text-xs font-bold transition-all ${autonomyMode === 'ask_first' ? 'bg-amber-500 text-white shadow-lg shadow-amber-500/30' : 'text-slate-400 hover:text-white hover:bg-slate-700/50'}`}>
              Ask First
            </button>
          </div>
        </div>
      </div>

      <div ref={containerRef} className="relative w-full h-[700px] bg-app-bg-card/50 rounded-3xl border border-app-border-light shadow-2xl overflow-hidden p-4">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(56,189,248,0.05)_0%,_transparent_70%)] pointer-events-none"></div>

        {/* Title & Live Status */}
        <div className="absolute top-8 left-8 z-20 flex flex-col gap-4">
          <div>
            <h3 className="text-3xl font-bold text-app-text-main">The Autonomous Loop</h3>
            <p className="text-app-text-label text-sm mt-1 max-w-sm">Observe the exact logic progression of the DSuite ecosystem in real-time.</p>
          </div>

          {/* Dynamic Video-like Status Indicator */}
          <div className="bg-slate-900/90 backdrop-blur border border-slate-700 p-4 rounded-xl shadow-2xl w-80">
            <p className="text-[10px] text-slate-400 font-mono uppercase tracking-widest mb-2 flex items-center justify-between">
              Live Flow Status
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            </p>
            <p className="text-sm font-semibold text-emerald-400 h-5 transition-all">{currentStepText}</p>
          </div>
        </div>

        <svg className="absolute inset-0 w-full h-full pointer-events-none z-0" viewBox="0 0 1200 700" preserveAspectRatio="xMidYMid meet">
          <defs>
            <linearGradient id="gradDsuite" x1="0" y1="0" x2="1200" y2="0" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.5" />
              <stop offset="100%" stopColor="#6366f1" stopOpacity="0.5" />
            </linearGradient>
            <linearGradient id="gradReturn" x1="1200" y1="0" x2="0" y2="0" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.5" />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.5" />
            </linearGradient>
            <filter id="glowFlow" filterUnits="userSpaceOnUse" x="-100" y="-100" width="1400" height="900">
              <feGaussianBlur stdDeviation="4" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Forward Paths */}
          <path className="path-upload" d="M 100 350 L 250 350" stroke="url(#gradDsuite)" strokeWidth="2" fill="none" strokeDasharray="5,5" />
          <path className="path-dsuite-nxdune" d="M 350 350 L 550 350" stroke="url(#gradDsuite)" strokeWidth="4" fill="none" filter="url(#glowFlow)" />
          <path className="path-nxdune-dev" d="M 650 350 C 750 350, 800 150, 950 150" stroke="url(#gradDsuite)" strokeWidth="4" fill="none" filter="url(#glowFlow)" />
          <path className="path-nxdune-test" d="M 650 350 L 950 350" stroke="url(#gradDsuite)" strokeWidth="4" fill="none" filter="url(#glowFlow)" />
          <path className="path-nxdune-deploy" d="M 650 350 C 750 350, 800 550, 950 550" stroke="url(#gradDsuite)" strokeWidth="4" fill="none" filter="url(#glowFlow)" />

          {/* Human Paths */}
          <path className="path-nxdune-human" d="M 650 350 C 680 350, 700 250, 750 250" stroke="url(#gradDsuite)" strokeWidth="4" fill="none" filter="url(#glowFlow)" opacity="0" />
          <path className="path-human-nxdune" d="M 750 250 C 700 250, 680 350, 650 350" stroke="url(#gradReturn)" strokeWidth="2" fill="none" strokeDasharray="5,5" filter="url(#glowFlow)" opacity="0" />
          <path className="path-dev-human" d="M 950 150 C 900 150, 880 250, 850 250" stroke="#f59e0b" strokeWidth="2" fill="none" strokeDasharray="5,5" filter="url(#glowFlow)" opacity="0" />

          <path className="path-nxdune-human-test" d="M 650 350 C 680 350, 700 450, 750 450" stroke="url(#gradDsuite)" strokeWidth="4" fill="none" filter="url(#glowFlow)" opacity="0" />
          <path className="path-human-test-nxdune" d="M 750 450 C 700 450, 680 350, 650 350" stroke="url(#gradReturn)" strokeWidth="2" fill="none" strokeDasharray="5,5" filter="url(#glowFlow)" opacity="0" />
          <path className="path-test-human" d="M 950 350 C 900 350, 880 450, 850 450" stroke="#ec4899" strokeWidth="2" fill="none" strokeDasharray="5,5" filter="url(#glowFlow)" opacity="0" />

          <path className="path-nxdune-human-deploy" d="M 650 350 C 680 350, 700 650, 750 650" stroke="url(#gradDsuite)" strokeWidth="4" fill="none" filter="url(#glowFlow)" opacity="0" />
          <path className="path-human-deploy-nxdune" d="M 750 650 C 700 650, 680 350, 650 350" stroke="url(#gradReturn)" strokeWidth="2" fill="none" strokeDasharray="5,5" filter="url(#glowFlow)" opacity="0" />
          <path className="path-deploy-human" d="M 950 550 C 900 550, 880 650, 850 650" stroke="#10b981" strokeWidth="2" fill="none" strokeDasharray="5,5" filter="url(#glowFlow)" opacity="0" />

          {/* Return Paths (Task updates) */}
          <path className="path-dev-nxdune" d="M 950 170 C 800 170, 750 370, 650 370" stroke="url(#gradReturn)" strokeWidth="2" fill="none" strokeDasharray="5,5" filter="url(#glowFlow)" />
          <path className="path-test-nxdune" d="M 950 370 C 800 370, 750 370, 650 370" stroke="url(#gradReturn)" strokeWidth="2" fill="none" strokeDasharray="5,5" filter="url(#glowFlow)" />
          <path className="path-deploy-nxdune" d="M 950 530 C 800 530, 750 370, 650 370" stroke="url(#gradReturn)" strokeWidth="2" fill="none" strokeDasharray="5,5" filter="url(#glowFlow)" />

          {/* Packets */}
          <rect className="packet-doc" width="16" height="20" rx="3" fill="#ffffff" stroke="#3b82f6" strokeWidth="2" x="-8" y="-10" />
          <circle className="packet-to-nxdune" r="6" fill="#6366f1" filter="url(#glowFlow)" />
          <circle className="packet-to-dev" r="5" fill="#a855f7" filter="url(#glowFlow)" />
          <circle className="packet-to-test" r="5" fill="#ec4899" filter="url(#glowFlow)" />
          <circle className="packet-to-deploy" r="5" fill="#10b981" filter="url(#glowFlow)" />

          {/* Human packets */}
          <circle className="packet-to-human" r="5" fill="#f59e0b" filter="url(#glowFlow)" opacity="0" />
          <circle className="packet-dev-to-human" r="5" fill="#f59e0b" filter="url(#glowFlow)" opacity="0" />
          <circle className="packet-human-to-nxdune" r="4" fill="#34d399" filter="url(#glowFlow)" opacity="0" />

          <circle className="packet-to-human-test" r="5" fill="#ec4899" filter="url(#glowFlow)" opacity="0" />
          <circle className="packet-test-to-human" r="5" fill="#ec4899" filter="url(#glowFlow)" opacity="0" />
          <circle className="packet-human-test-to-nxdune" r="4" fill="#34d399" filter="url(#glowFlow)" opacity="0" />

          <circle className="packet-to-human-deploy" r="5" fill="#10b981" filter="url(#glowFlow)" opacity="0" />
          <circle className="packet-deploy-to-human" r="5" fill="#10b981" filter="url(#glowFlow)" opacity="0" />
          <circle className="packet-human-deploy-to-nxdune" r="4" fill="#34d399" filter="url(#glowFlow)" opacity="0" />

          {/* Return Packets */}
          <circle className="packet-return-dev" r="4" fill="#34d399" filter="url(#glowFlow)" />
          <circle className="packet-return-test" r="4" fill="#34d399" filter="url(#glowFlow)" />
          <circle className="packet-return-deploy" r="4" fill="#34d399" filter="url(#glowFlow)" />
        </svg>

        <div className="absolute inset-0 z-10 w-full h-full max-w-[1200px] mx-auto pointer-events-none">
          {/* Start Point */}
          <div className="absolute top-[350px] left-[50px] -translate-x-1/2 -translate-y-1/2 text-center">
            <div className="w-12 h-16 bg-white border-2 border-slate-200 rounded-md shadow-md mx-auto mb-2 flex items-center justify-center">
              <FileText className="w-6 h-6 text-slate-400" />
            </div>
            <p className="text-xs font-bold text-app-text-main">Raw BRD</p>
          </div>

          {/* DSuite */}
          <div className="absolute top-[350px] left-[300px] -translate-x-1/2 -translate-y-1/2">
            <div className="dsuite-pulse absolute inset-0 bg-blue-500 rounded-3xl blur-xl opacity-0"></div>
            <div className="dsuite-ring absolute inset-0 rounded-3xl border-2 border-blue-500/50"></div>
            <div className="relative w-28 h-28 bg-app-bg-card border border-blue-500/30 rounded-3xl shadow-[0_0_30px_rgba(59,130,246,0.2)] flex flex-col items-center justify-center gap-2">
              <img src={Logo} alt="DSuite" className="w-10 h-10 object-contain" />
              <span className="text-xs font-bold text-blue-500">DSuite Master</span>
            </div>
          </div>

          {/* Nxdune */}
          <div className="absolute top-[350px] left-[600px] -translate-x-1/2 -translate-y-1/2">
            <div className="nxdune-pulse absolute inset-0 bg-indigo-500 rounded-2xl blur-xl opacity-0"></div>
            <div className="nxdune-ring absolute inset-0 rounded-2xl border-2 border-indigo-500/50"></div>
            <div className="relative w-32 h-24 bg-white border border-indigo-500/30 rounded-2xl shadow-[0_0_30px_rgba(99,102,241,0.2)] flex flex-col items-center justify-center p-3">
              <div className="absolute -top-3 px-2 py-0.5 bg-indigo-100 text-indigo-700 text-[9px] font-bold rounded-full border border-indigo-200 uppercase tracking-wider">The Hub</div>
              <img src={Logo1} alt="Nxdune" className="w-10 h-10 object-contain mb-1" />
              <span className="text-xs font-bold text-slate-800">Nxdune</span>
              <span className="text-[9px] text-slate-500">Task Router</span>
            </div>
          </div>

          {/* Human Dev Node */}
          <div className={`absolute top-[250px] left-[800px] -translate-x-1/2 -translate-y-1/2 transition-all duration-500 ${(executionMode === 'coexistence' || autonomyMode === 'ask_first') ? 'opacity-100 scale-100' : 'opacity-0 scale-50 pointer-events-none'}`}>
            <div className="human-pulse absolute inset-0 bg-amber-500 rounded-2xl blur-xl opacity-0"></div>
            <div className="human-ring absolute inset-0 rounded-2xl border-2 border-amber-500/50"></div>
            <div className="relative w-28 h-20 bg-white border border-amber-500/30 rounded-2xl shadow-[0_0_20px_rgba(245,158,11,0.15)] flex flex-col items-center justify-center p-2">
              <div className="absolute -top-3 px-2 py-0.5 bg-amber-100 text-amber-700 text-[9px] font-bold rounded-full border border-amber-200 uppercase tracking-wider">Human</div>
              <div className="w-8 h-8 rounded-full bg-amber-50 border border-amber-200 flex items-center justify-center mb-1">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-amber-600">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                  <circle cx="12" cy="7" r="4"></circle>
                </svg>
              </div>
              <span className="text-[10px] font-bold text-slate-800 text-center leading-tight">Developer / Approver</span>
            </div>
          </div>

          {/* Human QA Node */}
          <div className={`absolute top-[450px] left-[800px] -translate-x-1/2 -translate-y-1/2 transition-all duration-500 ${(executionMode === 'coexistence' || autonomyMode === 'ask_first') ? 'opacity-100 scale-100' : 'opacity-0 scale-50 pointer-events-none'}`}>
            <div className="human-qa-pulse absolute inset-0 bg-pink-500 rounded-2xl blur-xl opacity-0"></div>
            <div className="human-qa-ring absolute inset-0 rounded-2xl border-2 border-pink-500/50"></div>
            <div className="relative w-28 h-20 bg-white border border-pink-500/30 rounded-2xl shadow-[0_0_20px_rgba(236,72,153,0.15)] flex flex-col items-center justify-center p-2">
              <div className="absolute -top-3 px-2 py-0.5 bg-pink-100 text-pink-700 text-[9px] font-bold rounded-full border border-pink-200 uppercase tracking-wider">Human</div>
              <div className="w-8 h-8 rounded-full bg-pink-50 border border-pink-200 flex items-center justify-center mb-1">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-pink-600">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                  <circle cx="12" cy="7" r="4"></circle>
                </svg>
              </div>
              <span className="text-[10px] font-bold text-slate-800 text-center leading-tight">QA / Approver</span>
            </div>
          </div>

          {/* Human DevOps Node */}
          <div className={`absolute top-[650px] left-[800px] -translate-x-1/2 -translate-y-1/2 transition-all duration-500 ${(executionMode === 'coexistence' || autonomyMode === 'ask_first') ? 'opacity-100 scale-100' : 'opacity-0 scale-50 pointer-events-none'}`}>
            <div className="human-deploy-pulse absolute inset-0 bg-emerald-500 rounded-2xl blur-xl opacity-0"></div>
            <div className="human-deploy-ring absolute inset-0 rounded-2xl border-2 border-emerald-500/50"></div>
            <div className="relative w-28 h-20 bg-white border border-emerald-500/30 rounded-2xl shadow-[0_0_20px_rgba(16,185,129,0.15)] flex flex-col items-center justify-center p-2">
              <div className="absolute -top-3 px-2 py-0.5 bg-emerald-100 text-emerald-700 text-[9px] font-bold rounded-full border border-emerald-200 uppercase tracking-wider">Human</div>
              <div className="w-8 h-8 rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center mb-1">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-600">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                  <circle cx="12" cy="7" r="4"></circle>
                </svg>
              </div>
              <span className="text-[10px] font-bold text-slate-800 text-center leading-tight">DevOps / Approver</span>
            </div>
          </div>

          {/* Dev Agent (N-Mod) */}
          <div className="absolute top-[150px] left-[1000px] -translate-x-1/2 -translate-y-1/2">
            <div className="agent-pulse-dev absolute inset-0 bg-purple-500 rounded-2xl blur-xl opacity-0"></div>
            <div className="agent-ring-dev absolute inset-0 rounded-2xl border-2 border-purple-500/50"></div>
            <div className="relative flex items-center gap-3 bg-white border border-purple-200 rounded-2xl p-3 shadow-lg w-52">
              <div className="w-12 h-12 bg-slate-50 rounded-xl p-1.5 shrink-0 border border-slate-100 flex items-center justify-center">
                <img src={NModLogo} alt="N-Mod" className="w-full h-full object-contain" />
              </div>
              <div>
                <p className="text-xs font-bold text-slate-800 leading-tight">Dev Agent <span className="text-[10px] text-purple-500 ml-1">uses N-Mod</span></p>
                <p className="text-[10px] text-slate-500 mt-0.5">Builds code iterative workflow.</p>
              </div>
            </div>
          </div>

          {/* Test Agent (Kaktox) */}
          <div className="absolute top-[350px] left-[1000px] -translate-x-1/2 -translate-y-1/2">
            <div className="agent-pulse-test absolute inset-0 bg-pink-500 rounded-2xl blur-xl opacity-0"></div>
            <div className="agent-ring-test absolute inset-0 rounded-2xl border-2 border-pink-500/50"></div>
            <div className="relative flex items-center gap-3 bg-white border border-pink-200 rounded-2xl p-3 shadow-lg w-52">
              <div className="w-12 h-12 bg-slate-50 rounded-xl p-1 shrink-0 border border-slate-100 flex items-center justify-center">
                <img src={KaktoxLogo} alt="Kaktox" className="w-full h-full object-contain" />
              </div>
              <div>
                <p className="text-xs font-bold text-slate-800 leading-tight">Test Agent <span className="text-[10px] text-pink-500 ml-1">uses Kaktox</span></p>
                <p className="text-[10px] text-slate-500 mt-0.5">Executes rigorous automated tests.</p>
              </div>
            </div>
          </div>

          {/* Deploy Agent (CloudSpx) */}
          <div className="absolute top-[550px] left-[1000px] -translate-x-1/2 -translate-y-1/2">
            <div className="agent-pulse-deploy absolute inset-0 bg-emerald-500 rounded-2xl blur-xl opacity-0"></div>
            <div className="agent-ring-deploy absolute inset-0 rounded-2xl border-2 border-emerald-500/50"></div>
            <div className="relative flex items-center gap-3 bg-white border border-emerald-200 rounded-2xl p-3 shadow-lg w-52">
              <div className="w-12 h-12 bg-slate-50 rounded-xl p-1 shrink-0 border border-slate-100 flex items-center justify-center">
                <img src={CloudSpxLogo} alt="CloudSpx" className="w-full h-full object-contain" />
              </div>
              <div>
                <p className="text-xs font-bold text-slate-800 leading-tight">Deploy Agent <span className="text-[10px] text-emerald-500 ml-1">uses CloudSpx</span></p>
                <p className="text-[10px] text-slate-500 mt-0.5">Pushes verified builds to prod.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const VideoExplainer = () => {
  const container = useRef(null);
  const progressBarRef = useRef(null);
  const timeTextRef = useRef(null);
  const audioContextRef = useRef(null);
  const soundEnabledRef = useRef(false);
  const activeNarrationDoneRef = useRef(null);
  const preferredVoiceRef = useRef(null);
  const isPlaying = true;
  const [soundEnabled, setSoundEnabled] = useState(false);

  useEffect(() => {
    soundEnabledRef.current = soundEnabled;
    if (!soundEnabled && typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel();
      if (activeNarrationDoneRef.current) {
        activeNarrationDoneRef.current();
        activeNarrationDoneRef.current = null;
      }
    }
  }, [soundEnabled]);

  useEffect(() => {
    return () => {
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => { });
        audioContextRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return;
    const synth = window.speechSynthesis;

    const pickPreferredFemaleVoice = () => {
      const voices = synth.getVoices();
      if (!voices || voices.length === 0) return null;

      const englishVoices = voices.filter((voice) => (voice.lang || '').toLowerCase().startsWith('en'));
      const voicePool = englishVoices.length ? englishVoices : voices;

      const femalePriority = [
        /Aria|Jenny|Sonia|Ava|Emma|Olivia|Samantha|Victoria|Zira|Hazel|Female/i,
        /Google US English/i,
        /en-US|en-GB/i
      ];

      for (const pattern of femalePriority) {
        const found = voicePool.find((voice) => pattern.test(`${voice.name} ${voice.lang}`));
        if (found) return found;
      }

      return voicePool[0] || null;
    };

    const setVoice = () => {
      preferredVoiceRef.current = pickPreferredFemaleVoice();
    };

    setVoice();
    synth.addEventListener('voiceschanged', setVoice);
    return () => synth.removeEventListener('voiceschanged', setVoice);
  }, []);

  const getAudioContext = () => {
    if (typeof window === 'undefined') return null;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return null;
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContextClass();
    }
    return audioContextRef.current;
  };

  const playSoundCue = (cueName) => {
    if (!soundEnabledRef.current) return;
    const ctx = getAudioContext();
    if (!ctx) return;
    if (ctx.state === 'suspended') {
      ctx.resume().catch(() => { });
    }

    const cueMap = {
      upload: [392],
      analyze: [440, 523],
      approved: [659],
      route: [523, 659],
      dev: [587],
      test: [659],
      deploy: [740],
      success: [740, 880, 988],
      done: [660]
    };

    const frequencies = cueMap[cueName] || [523];
    const waveType = cueName === 'success' ? 'triangle' : 'sine';
    const baseVolume = cueName === 'success' ? 0.035 : 0.022;
    const now = ctx.currentTime;

    frequencies.forEach((freq, index) => {
      const start = now + index * 0.08;
      const end = start + 0.1;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = waveType;
      osc.frequency.setValueAtTime(freq, start);
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(baseVolume, start + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, end);

      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(start);
      osc.stop(end + 0.01);
    });
  };

  const speakScript = (text) => {
    if (!soundEnabledRef.current) return Promise.resolve();
    if (typeof window === 'undefined' || !window.speechSynthesis || !window.SpeechSynthesisUtterance) {
      return Promise.resolve();
    }

    const synth = window.speechSynthesis;
    return new Promise((resolve) => {
      try {
        synth.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        const voice = preferredVoiceRef.current;
        if (voice) {
          utterance.voice = voice;
        }
        utterance.lang = (voice && voice.lang) || 'en-US';
        utterance.rate = 0.88;
        utterance.pitch = 0.98;
        utterance.volume = 0.9;

        let finished = false;
        const finish = () => {
          if (finished) return;
          finished = true;
          if (activeNarrationDoneRef.current === finish) {
            activeNarrationDoneRef.current = null;
          }
          resolve();
        };

        const timeoutMs = Math.max(1400, text.length * 75);
        const timeoutId = window.setTimeout(finish, timeoutMs);

        utterance.onend = () => {
          window.clearTimeout(timeoutId);
          finish();
        };
        utterance.onerror = () => {
          window.clearTimeout(timeoutId);
          finish();
        };

        activeNarrationDoneRef.current = finish;
        synth.speak(utterance);
      } catch {
        resolve();
      }
    });
  };

  const toggleSound = () => {
    setSoundEnabled((prev) => {
      const next = !prev;
      if (next) {
        const ctx = getAudioContext();
        if (ctx && ctx.state === 'suspended') {
          ctx.resume().catch(() => { });
        }
      }
      return next;
    });
  };

  useLayoutEffect(() => {
    let ctx = gsap.context(() => {
      const tl = gsap.timeline({
        repeat: -1,
        onUpdate: function () {
          const p = this.progress();

          if (progressBarRef.current) {
            progressBarRef.current.style.width = (p * 100) + "%";
          }

          if (timeTextRef.current) {
            const totalSeconds = 85;
            const currentSeconds = Math.floor(totalSeconds * p);
            const mins = Math.floor(currentSeconds / 60);
            const secs = currentSeconds % 60;
            timeTextRef.current.innerText = `0${mins}:${secs < 10 ? '0' : ''}${secs} / 01:25`;
          }
        }
      });

      const pauseForNarration = (cueName, text) => () => {
        playSoundCue(cueName);
        tl.pause();
        speakScript(text).finally(() => {
          if (tl.paused()) {
            tl.resume();
          }
        });
      };

      // Reset only individual scene nodes; keep the shared agent-row wrapper visible.
      tl.set(['.doc-icon', '.dsuite-node', '.conn-beam', '.nxdune-node', '.success-burst'], { opacity: 0, scale: 0.5 })
        .set('.text-overlay', { opacity: 0, y: 20 })
        .set('.laser', { scaleX: 0, opacity: 0 })
        .set('.task-card', { opacity: 0, y: 20 })
        .set('.dsuite-approved', { opacity: 0, scale: 0.7, y: 4 })
        .set('.code-lines', { opacity: 0, y: -6 })
        .set('.code-lines div', { opacity: 0, x: -10 });

      // -- SCENE 1: Document Upload --
      tl.call(pauseForNarration('upload', 'Document is uploaded.'))
        .to('.text-s1', { opacity: 1, y: 0, duration: 0.5 })
        .to('.doc-icon', { opacity: 1, scale: 1, duration: 0.8, ease: "back.out(1.5)" })
        .to('.doc-icon', { y: -10, duration: 1, yoyo: true, repeat: 1, ease: "sine.inOut" })
        .to('.text-s1', { opacity: 0, y: -20, duration: 0.5 })
        .to('.doc-icon', { opacity: 0, scale: 0, duration: 0.5 });

      // -- SCENE 2: DSuite Analysis --
      tl.call(pauseForNarration('analyze', 'Dee Suite analyzes and approves architecture.'))
        .to('.text-s2', { opacity: 1, y: 0, duration: 0.5 }, "-=0.2")
        .to('.dsuite-node', { opacity: 1, scale: 1, duration: 0.8, ease: "back.out(1.5)" })
        // Laser Scan effect
        .to('.laser', { opacity: 1, duration: 0.2 })
        .to('.laser', { scaleX: 1, duration: 1, ease: "power2.inOut" })
        .to('.laser', { opacity: 0, duration: 0.2 })
        .to('.dsuite-approved', { opacity: 1, scale: 1, y: 0, duration: 0.35, ease: "back.out(1.6)" })
        .call(pauseForNarration('approved', 'Architecture approved by Dee Suite.'))
        .to('.text-s2', { opacity: 0, y: -20, duration: 0.5, delay: 0.5 })
        .to('.dsuite-node', { x: -150, duration: 0.8, ease: "power3.inOut" }); // Move left to make room

      // -- SCENE 3: Nxdune Orchestration --
      tl.call(pauseForNarration('route', 'Nex Dune creates tasks and routes work to agents.'))
        .to('.text-s3', { opacity: 1, y: 0, duration: 0.5 }, "-=0.5")
        .to('.nxdune-node', { opacity: 1, scale: 1, x: 150, duration: 0.8, ease: "back.out(1.5)" }, "-=0.5")
        // Beam connecting them
        .to('.conn-beam', { opacity: 1, scaleX: 1, duration: 0.5 })
        // Task cards popping out of Nxdune
        .to('.task-card', { opacity: 1, y: 0, stagger: 0.2, duration: 0.5, ease: "back.out(2)" })
        .to('.conn-beam', { opacity: 0, duration: 0.2, delay: 0.5 })
        .to('.dsuite-node', { opacity: 0, scale: 0, duration: 0.5 }, "-=0.2")
        .to('.text-s3', { opacity: 0, y: -20, duration: 0.5 })
        .to('.nxdune-node', { y: -100, x: 0, duration: 0.8, ease: "power3.inOut" })
        .to('.task-card', { opacity: 0, duration: 0.3 }, "-=0.8");

      // -- SCENE 4: Agents Executing sequentially --
      tl.to('.text-s4', { opacity: 1, y: 0, duration: 0.5 }, "-=0.2")
        // All agents appear at bottom in standby
        .to(['.nmod-node', '.kaktox-node', '.cloudspx-node'], { opacity: 1, scale: 1, stagger: 0.1, duration: 0.4, ease: "back.out(1.5)" })
        .to('.text-s4', { opacity: 0, y: -20, duration: 0.3, delay: 0.5 }) // Hide generic text

        // 1. DEV TASK -> N-Mod
        .to('.text-dev', { opacity: 1, y: 0, duration: 0.3 })
        .call(pauseForNarration('dev', 'Dev agent on N Mod E X T is coding and finishing the task.'))
        .to('.task-beam-dev', { opacity: 1, scaleY: 1, duration: 0.3 })
        .to('.code-lines', { opacity: 1, y: 0, duration: 0.2 })
        .to('.code-lines div', { opacity: 1, x: 0, stagger: 0.1, duration: 0.5 })
        .to('.nmod-node', { scale: 1.1, boxShadow: "0px 0px 30px #a855f7", duration: 0.3, yoyo: true, repeat: 1 })
        .to('.nmod-check', { opacity: 1, scale: 1, duration: 0.3 })
        .to('.code-lines', { opacity: 0, y: -6, duration: 0.2 })
        .to('.task-beam-dev', { opacity: 0, duration: 0.2 })
        .to('.text-dev', { opacity: 0, y: -20, duration: 0.3, delay: 0.5 })

        // 2. TEST TASK -> Kaktox
        .to('.text-test', { opacity: 1, y: 0, duration: 0.3 })
        .call(pauseForNarration('test', 'Test agent on Kak Tox validates the build and all tests pass.'))
        .to('.task-beam-test', { opacity: 1, scaleY: 1, duration: 0.3 })
        .to('.kaktox-node', { scale: 1.1, boxShadow: "0px 0px 30px #ec4899", duration: 0.3, yoyo: true, repeat: 1 })
        .to('.kaktox-check', { opacity: 1, scale: 1, duration: 0.3 })
        .to('.task-beam-test', { opacity: 0, duration: 0.2 })
        .to('.text-test', { opacity: 0, y: -20, duration: 0.3, delay: 0.5 })

        // 3. DEPLOY TASK -> CloudSpx
        .to('.text-deploy', { opacity: 1, y: 0, duration: 0.3 })
        .call(pauseForNarration('deploy', 'Deploy agent on Cloud S P X is deploying the verified build.'))
        .to('.task-beam-deploy', { opacity: 1, scaleY: 1, duration: 0.3 })
        .to('.cloudspx-node', { scale: 1.1, boxShadow: "0px 0px 30px #10b981", duration: 0.3, yoyo: true, repeat: 1 })
        .to('.cloudspx-check', { opacity: 1, scale: 1, duration: 0.3 })
        .to('.task-beam-deploy', { opacity: 0, duration: 0.2 })
        .to('.text-deploy', { opacity: 0, y: -20, duration: 0.3, delay: 0.5 });

      // -- SCENE 5: Success --
      tl.to('.text-s5', { opacity: 1, y: 0, scale: 1.2, duration: 0.5 })
        .call(pauseForNarration('success', 'Application is live.'))
        .to('.success-burst', { opacity: 1, scale: 5, duration: 1, ease: "power2.out" })
        .call(() => playSoundCue('done'))
        .to({}, { duration: 1.5 }); // Final pause

    }, container);
    return () => ctx.revert();
  }, []);

  return (
    <div ref={container} className="w-full max-w-5xl mx-auto my-8 bg-app-bg-card rounded-[2rem] border border-app-border-light shadow-2xl overflow-hidden relative aspect-video font-sans">

      {/* Fake Header */}
      <div className="absolute top-0 left-0 right-0 z-40 flex items-center px-4 py-3 bg-gradient-to-b from-slate-100/80 to-transparent border-b border-app-border-light/50">
        <div className="flex gap-2">
          <div className="w-3 h-3 rounded-full bg-red-400"></div>
          <div className="w-3 h-3 rounded-full bg-yellow-400"></div>
          <div className="w-3 h-3 rounded-full bg-green-400"></div>
        </div>
        <p className="mx-auto text-xs text-app-text-label font-mono">DSuite-Workflow-Explainer.mp4</p>
      </div>

      {/* Video Content Canvas */}
      <div className="absolute inset-0 z-10 flex items-center justify-center overflow-hidden bg-app-bg-card">
        {/* Background Grid */}
        <div className="absolute inset-0 bg-[linear-gradient(rgba(0,0,0,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(0,0,0,0.03)_1px,transparent_1px)] bg-[size:40px_40px]"></div>

        {/* --- SCENE TEXT OVERLAYS --- */}
        <div className="absolute top-16 md:top-20 z-30 w-full text-center scene-text pointer-events-none px-4">
          <h2 className="text-overlay opacity-0 text-s1 text-2xl md:text-4xl font-bold text-app-text-main absolute w-full left-0">1. Document is Uploaded</h2>
          <h2 className="text-overlay opacity-0 text-s2 text-2xl md:text-4xl font-bold text-blue-600 absolute w-full left-0">2. DSuite Analyzes & Approves Architecture</h2>
          <h2 className="text-overlay opacity-0 text-s3 text-2xl md:text-4xl font-bold text-indigo-600 absolute w-full left-0">3. Nxdune Creates Tasks & Routes to Agents</h2>
          <h2 className="text-overlay opacity-0 text-s4 text-2xl md:text-4xl font-bold text-slate-800 absolute w-full left-0">4. Agents Execute in Sequence...</h2>
          <h2 className="text-overlay opacity-0 text-dev text-2xl md:text-4xl font-bold text-purple-600 absolute w-full left-0">Dev Agent (N-Mod EXT) is coding... Done.</h2>
          <h2 className="text-overlay opacity-0 text-test text-2xl md:text-4xl font-bold text-pink-600 absolute w-full left-0">Test Agent (Kaktox) is testing... Passed 100%.</h2>
          <h2 className="text-overlay opacity-0 text-deploy text-2xl md:text-4xl font-bold text-emerald-600 absolute w-full left-0">Deploy Agent (CloudSpx) is deploying...</h2>
          <h2 className="text-overlay opacity-0 text-s5 text-3xl md:text-5xl font-extrabold text-emerald-600 absolute w-full left-0">Application is Live!</h2>
        </div>

        {/* --- MOTION GRAPHIC ELEMENTS --- */}
        <div className="scene-elements relative w-full h-[60%] flex items-center justify-center z-20 pointer-events-none scale-75 md:scale-100 mt-10">

          {/* S1: Document */}
          <div className="doc-icon opacity-0 scale-50 absolute flex flex-col items-center">
            <div className="bg-white p-4 rounded-2xl shadow-xl border border-slate-200">
              <FileText className="w-20 h-20 text-blue-500" />
            </div>
            <div className="w-16 h-2 bg-blue-500/20 rounded-full mt-4 blur-sm"></div>
          </div>

          {/* S2: DSuite */}
          <div className="dsuite-node opacity-0 scale-50 absolute z-20 flex flex-col items-center justify-center w-32 h-32 bg-white border border-blue-200 rounded-3xl shadow-xl">
            <div className="flex flex-col items-center leading-none">
              <span className="text-xl font-extrabold tracking-tight text-blue-600">DSuite</span>
              <span className="text-[9px] font-semibold tracking-[0.12em] uppercase text-blue-500/80 mt-1">Master</span>
            </div>
            <div className="dsuite-approved absolute -bottom-4 left-1/2 -translate-x-1/2 opacity-0 scale-75">
              <div className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 shadow-sm">
                <CheckCircle className="h-3 w-3 text-emerald-600" />
                <span className="text-[9px] font-bold uppercase tracking-wide text-emerald-700">Approved</span>
              </div>
            </div>
            <div className="laser absolute top-1/2 left-0 w-full h-1 bg-blue-400 shadow-[0_0_10px_#60a5fa] origin-left"></div>
          </div>

          {/* Beam DSuite to Nxdune */}
          <div className="conn-beam absolute z-0 w-[172px] h-1.5 bg-gradient-to-r from-blue-400 to-indigo-400 origin-left opacity-0 rounded-full"></div>

          {/* S3: Nxdune */}
          <div className="nxdune-node opacity-0 scale-50 absolute z-20 flex flex-col items-center justify-center w-32 h-32 bg-white border border-indigo-200 rounded-3xl shadow-xl">
            <img src={Logo1} alt="Nxdune" className="w-16 h-16 object-contain" />

            {/* Task Cards */}
            <div className="absolute -right-24 top-0 flex flex-col gap-2">
              <div className="task-card opacity-0 w-20 h-8 bg-purple-100 rounded border border-purple-300 shadow-sm flex items-center px-2"><div className="w-full h-1 bg-purple-300 rounded"></div></div>
              <div className="task-card opacity-0 w-20 h-8 bg-pink-100 rounded border border-pink-300 shadow-sm flex items-center px-2"><div className="w-full h-1 bg-pink-300 rounded"></div></div>
              <div className="task-card opacity-0 w-20 h-8 bg-emerald-100 rounded border border-emerald-300 shadow-sm flex items-center px-2"><div className="w-full h-1 bg-emerald-300 rounded"></div></div>
            </div>
          </div>

          {/* S4: Agents */}
          <div className="absolute bottom-[-20px] w-full max-w-[600px] flex justify-between px-10">

            {/* Beams pointing down */}
            <div className="task-beam-dev opacity-0 absolute left-[80px] -top-[100px] w-1.5 h-[80px] bg-gradient-to-b from-indigo-400 to-purple-400 origin-top opacity-0 rounded-full"></div>
            <div className="task-beam-test opacity-0 absolute left-[300px] -top-[100px] w-1.5 h-[80px] bg-gradient-to-b from-pink-300 to-pink-500 origin-top opacity-0 rounded-full"></div>
            <div className="task-beam-deploy opacity-0 absolute right-[80px] -top-[100px] w-1.5 h-[80px] bg-gradient-to-b from-indigo-400 to-emerald-400 origin-top opacity-0 rounded-full"></div>

            <div className="nmod-node opacity-0 scale-50 relative flex flex-col items-center justify-center w-28 h-28 bg-white border border-purple-200 rounded-2xl shadow-lg">
              <img src={NModLogo} alt="N-Mod" className="w-14 h-14 object-contain" />
              <p className="mt-1 text-[9px] font-bold uppercase tracking-wide text-purple-700">Dev Agent</p>
              <div className="code-lines absolute -top-10 flex flex-col gap-1 w-full bg-slate-800 p-2 rounded-lg shadow-md">
                <div className="opacity-0 w-full h-1.5 bg-purple-400 rounded"></div>
                <div className="opacity-0 w-3/4 h-1.5 bg-purple-400 rounded"></div>
                <div className="opacity-0 w-1/2 h-1.5 bg-purple-400 rounded"></div>
              </div>
              <CheckCircle className="nmod-check absolute -bottom-3 -right-3 w-8 h-8 text-purple-500 opacity-0 bg-white rounded-full shadow-md" />
            </div>

            <div className="kaktox-node opacity-0 scale-50 relative flex flex-col items-center justify-center w-28 h-28 bg-white border border-pink-200 rounded-2xl shadow-lg">
              <img src={KaktoxLogo} alt="Kaktox" className="w-14 h-14 object-contain" />
              <p className="mt-1 text-[9px] font-bold uppercase tracking-wide text-pink-600">Test Agent</p>
              <CheckCircle className="kaktox-check absolute -bottom-3 -right-3 w-8 h-8 text-pink-500 opacity-0 bg-white rounded-full shadow-md" />
            </div>

            <div className="cloudspx-node opacity-0 scale-50 relative flex flex-col items-center justify-center w-28 h-28 bg-white border border-emerald-200 rounded-2xl shadow-lg">
              <img src={CloudSpxLogo} alt="CloudSpx" className="w-14 h-14 object-contain" />
              <p className="mt-1 text-[9px] font-bold uppercase tracking-wide text-emerald-600">Deploy Agent</p>
              <CheckCircle className="cloudspx-check absolute -bottom-3 -right-3 w-8 h-8 text-emerald-500 opacity-0 bg-white rounded-full shadow-md" />
            </div>
          </div>

          {/* S5: Final Burst */}
          <div className="success-burst absolute w-32 h-32 bg-emerald-400/30 rounded-full blur-2xl opacity-0"></div>

        </div>
      </div>

      {/* Fake Video Controls */}
      <div className="absolute bottom-0 left-0 right-0 z-40 bg-white/95 border-t border-slate-200 p-4 pt-6 backdrop-blur-sm shadow-[0_-10px_30px_rgba(0,0,0,0.05)]">

        {/* Progress Bar */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-slate-100 cursor-pointer overflow-hidden">
          <div ref={progressBarRef} className="h-full bg-blue-500 transition-all duration-75" style={{ width: `0%` }}></div>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6 text-slate-800">
            {/* Play/Pause icon (mock) */}
            {isPlaying ?
              <div className="flex gap-1 items-center justify-center w-4 h-4 cursor-pointer hover:scale-110">
                <div className="w-1.5 h-4 bg-slate-800 rounded-sm"></div>
                <div className="w-1.5 h-4 bg-slate-800 rounded-sm"></div>
              </div>
              :
              <div className="w-0 h-0 border-t-[8px] border-b-[8px] border-l-[12px] border-t-transparent border-b-transparent border-l-slate-800 cursor-pointer hover:scale-110"></div>
            }
            <span ref={timeTextRef} className="text-xs font-mono text-slate-500">00:00 / 01:25</span>
          </div>

          <div className="flex items-center gap-4 text-slate-500">
            <span className="text-[10px] uppercase tracking-widest border border-slate-200 bg-slate-50 px-2 py-1 rounded">Auto-Generated Visuals</span>
            <button
              type="button"
              onClick={toggleSound}
              className={`inline-flex items-center gap-1.5 text-[10px] uppercase tracking-widest border px-2 py-1 rounded transition-colors ${soundEnabled
                ? 'text-emerald-700 border-emerald-200 bg-emerald-50'
                : 'text-slate-600 border-slate-200 bg-slate-50'
                }`}
            >
              {soundEnabled ? <Volume2 className="h-3.5 w-3.5" /> : <VolumeX className="h-3.5 w-3.5" />}
              <span>{soundEnabled ? 'Narration On' : 'Narration Off'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

const ProcessCard = ({ number, title, text, image, imageBg, reverse = false }) => {
  const containerRef = useRef(null);
  const textRef = useRef(null);
  const imageRef = useRef(null);

  useEffect(() => {
    let ctx = gsap.context(() => {
      // Timeline for scroll interactions
      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: containerRef.current,
          start: "top 75%", // Triggers slightly before section hits center
          end: "bottom 25%",
          toggleActions: "play reverse play reverse", // Animates securely scrolling up and down
        }
      });

      // Text animation: Slide in and fade up
      tl.from(textRef.current, {
        x: reverse ? 50 : -50,
        opacity: 0,
        duration: 0.8,
        ease: "power3.out"
      });

      // Image animation: Scale, rotate slightly, and pop
      tl.from(imageRef.current, {
        x: reverse ? -50 : 50,
        scale: 0.8,
        rotation: reverse ? -5 : 5,
        opacity: 0,
        duration: 1,
        ease: "back.out(1.5)"
      }, "-=0.6"); // Overlap animation slightly

    }, containerRef);
    return () => ctx.revert();
  }, [reverse]);

  return (
    <div ref={containerRef} className={`flex flex-col ${reverse ? 'md:flex-row-reverse' : 'md:flex-row'} items-center gap-12 lg:gap-20 py-24 border-b border-app-border-light relative overflow-hidden group`}>

      {/* Background ambient glow effect on hover/scroll */}
      <div className={`absolute top-1/2 ${reverse ? 'left-1/4' : 'right-1/4'} -translate-y-1/2 w-[500px] h-[500px] bg-gradient-to-br ${imageBg.replace('bg-', 'from-').replace('border-', 'to-')} opacity-0 group-hover:opacity-10 transition-opacity duration-1000 rounded-full blur-[100px] pointer-events-none -z-10`} />

      {/* Text Context */}
      <div ref={textRef} className="flex-1 w-full space-y-6 relative z-10">
        <div className="inline-flex items-center gap-3 px-4 py-2 bg-app-bg-card border border-app-border-light rounded-full shadow-sm text-app-primary text-sm font-bold tracking-widest uppercase">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-app-primary"></span>
          </span>
          Step 0{number}
        </div>
        <h3 className="text-4xl sm:text-5xl font-extrabold text-app-text-main leading-tight mb-2">
          {title.split('â†’').map((part, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span className="text-app-primary/50 mx-2">â†’</span>}
              {part.trim()}
            </React.Fragment>
          ))}
        </h3>
        <p className="text-xl text-app-text-label leading-relaxed max-w-xl">
          {text}
        </p>
      </div>

      {/* Visual Context */}
      <div ref={imageRef} className={`flex-1 w-full flex justify-center ${reverse ? 'md:justify-start' : 'md:justify-end'} relative z-10`}>
        <div className={`relative w-full max-w-md aspect-square ${imageBg} rounded-[3rem] p-1 shadow-2xl flex flex-col items-center justify-center overflow-hidden border border-white/50 backdrop-blur-xl group-hover:scale-[1.02] hover:shadow-blue-500/20 transition-all duration-700`}>

          <div className="absolute inset-0 bg-white/40 group-hover:bg-white/60 transition-colors duration-700" />
          <div className="absolute top-0 right-0 w-40 h-40 bg-white/40 rounded-full blur-3xl -mt-10 -mr-10 transition-transform group-hover:scale-150 duration-1000" />
          <div className="absolute bottom-0 left-0 w-40 h-40 bg-black/5 rounded-full blur-3xl -mb-10 -ml-10" />

          {/* Main Icon Box */}
          <div className="relative z-10 w-40 h-40 bg-white rounded-[2rem] shadow-xl border border-slate-100/50 flex items-center justify-center p-6 transform group-hover:-translate-y-4 group-hover:shadow-2xl transition-all duration-700 group-hover:border-app-primary/20 bg-clip-padding backdrop-filter backdrop-blur-xl bg-opacity-90">
            {image ? (
              <img src={image} className="w-full h-full object-contain drop-shadow-lg group-hover:scale-110 transition-transform duration-700" alt={title} />
            ) : (
              <FileText className="w-20 h-20 text-slate-800" />
            )}
          </div>

          {/* Status Label */}
          <div className="relative z-10 mt-8 bg-white/95 backdrop-blur-xl px-6 py-3 rounded-full border border-slate-200 shadow-lg opacity-90 group-hover:opacity-100 group-hover:translate-y-0 translate-y-2 transition-all duration-700 flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-app-status-success shadow-[0_0_10px_rgba(16,185,129,0.5)] animate-pulse" />
            <p className="text-sm font-bold tracking-widest text-slate-800 uppercase">{title.split('â†’')[0].trim()}</p>
          </div>

        </div>
      </div>
    </div>
  );
};


const HowItWorks = () => {
  return (
    <div className="min-h-screen bg-app-bg-page text-app-text-main font-sans">
      <nav className="w-full bg-app-bg-card/90 backdrop-blur-md z-40 border-b border-app-border-light sticky top-0">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="flex items-center gap-3">
              <img src={Logo} alt="DSuite" className="h-9 w-auto" />
              <div className="h-6 w-px bg-app-bg-hover" />
              <span className="text-lg font-bold tracking-tight text-app-text-main">
                DSuite
              </span>
            </Link>
            <div className="flex items-center gap-3">
              <Link to="/" className="text-sm font-medium text-app-text-label hover:text-app-text-main transition-colors">
                Back to home
              </Link>
              <Link to="/login" className="hidden sm:inline-flex text-sm font-semibold text-app-text-label px-3 py-1.5 rounded-lg hover:bg-app-bg-page border border-app-border transition-colors">
                Log in
              </Link>
              <Link to="/signup" className="inline-flex items-center text-sm font-semibold text-white bg-app-primary hover:bg-app-primary-hover px-4 py-2 rounded-lg shadow-sm shadow-blue-500/30 transition-colors">
                Get started
                <ArrowRight className="ml-1.5 h-4 w-4" />
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-20 pb-16 px-4 bg-app-bg-card relative overflow-hidden border-b border-app-border-light">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.1)_0%,_transparent_60%)] pointer-events-none" />
        <div className="max-w-4xl mx-auto text-center relative z-10">
          <div className="inline-flex items-center justify-center p-3 sm:p-4 bg-blue-50 rounded-2xl mb-8 border border-blue-100 shadow-inner">
            <div className="flex items-center justify-center gap-3">
              <img src={Logo} alt="DSuite" className="h-9 w-auto" />
              <div className="h-6 w-px bg-blue-200" />
              <span className="text-xl font-bold tracking-tight text-app-text-main">
                DSuite
              </span>
            </div>
          </div>
          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight text-app-text-main mb-6 leading-tight">
            One Document. <br /> Autonomous Engineering.
          </h1>
          <p className="text-xl sm:text-2xl text-app-text-label leading-relaxed max-w-2xl mx-auto">
            Discover how DSuite orchestrates a highly-specialized swarm of AI agents to instantly build, test, and deploy software from a single requirements document.
          </p>
        </div>
      </section>

      {/* Video-Style Flow Explainer (temporarily commented out, keep for later) */}
      {/*
      <section className="py-16 bg-app-bg-page px-4 border-b border-app-border-light">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-4">
            <h2 className="text-3xl font-bold text-app-text-main mb-2">Watch the Logic Pipeline</h2>
            <p className="text-app-text-label">See the exact step-by-step sequence of automation in real-time.</p>
          </div>
          <VideoExplainer />
        </div>
      </section>
      */}

      {/* Structured Narrative Story */}
      <section className="py-10 bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">

          <ProcessCard
            number="1"
            title="DSuite Master Analysis"
            text="You drop your BRD into DSuite. The DSuite Master Agent parses everythingâ€”business rules, architecture, data schemas, and non-functional requirements. It evaluates if the project is 'Sandbox Ready' and extracts a complete blueprint."
            image={Logo}
            imageBg="bg-blue-50 border-blue-200"
            reverse={false}
          />

          <ProcessCard
            number="2"
            title="Nxdune Orchestration"
            text="The DSuite blueprint is instantly piped to Nxdune. Nxdune creates your organizational workspace and breaks the blueprint down into granular sub-tasks, organizing them dynamically into test, dev, and deploy tickets on an automated Kanban."
            image={Logo1}
            imageBg="bg-indigo-50 border-indigo-200"
            reverse={true}
          />

          <ProcessCard
            number="3"
            title="Dev Tasks â†’ N-Mod"
            text="As soon as tasks appear in Nxdune, the Dev Agent picks them up. Connecting directly to N-Mod, the Dev Agent starts actively writing, refactoring, and structuring the codebase iteratively. The agent operates N-Mod just like a human engineer would."
            image={NModLogo}
            imageBg="bg-purple-50 border-purple-200"
            reverse={false}
          />

          <ProcessCard
            number="4"
            title="Test Tasks â†’ Kaktox"
            text="When N-Mod finishes a component, Nxdune assigns the testing ticket to the Test Agent. It spins up Kaktox, which autonomously writes unit tests, executes integration flows, and validates logic to ensure 0% failure rate before it ever moves forward."
            image={KaktoxLogo}
            imageBg="bg-pink-50 border-pink-200"
            reverse={true}
          />

          <ProcessCard
            number="5"
            title="Deploy Tasks â†’ CloudSpx"
            text="Green across the board? The Deploy Agent handles the final stage. It takes the repository that cleared Kaktox and pushes it through secure pipelines into CloudSpx. Your application is now live, all tracked directly back inside Nxdune."
            image={CloudSpxLogo}
            imageBg="bg-emerald-50 border-emerald-200"
            reverse={false}
          />

        </div>
      </section>

      {/* The Animated Chart */}
      <section className="py-24 bg-slate-50 border-t border-app-border-light relative overflow-hidden">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
          <div className="text-center max-w-3xl mx-auto">
            <h2 className="text-4xl font-extrabold text-app-text-main mb-4">The Complete Logic Flow</h2>
            <p className="text-lg text-app-text-label">Observe how DSuite triggers the workflow, how Nxdune distributes tasks to the specialized agents, and how progress metrics flow back constantly.</p>
          </div>

          <AnimatedWorkflowDiagram />

        </div>
      </section>

      {/* Summary CTA */}
      <section className="py-20 sm:py-24 bg-app-text-main text-white relative overflow-hidden text-center z-10 border-t border-app-border-light">
        <div className="absolute inset-0 opacity-20 mix-blend-overlay bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.2),_transparent_60%),radial-gradient(circle_at_bottom,_rgba(129,140,248,0.25),_transparent_55%)]" />
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
          <h2 className="text-3xl sm:text-5xl font-bold mb-6 tracking-tight">
            Watch the agents work.
          </h2>
          <p className="text-lg sm:text-xl text-slate-300 max-w-2xl mx-auto mb-10">
            Upload a document into DSuite today and let the ecosystem plan, code, test, and deploy for you.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link to="/signup" className="inline-flex items-center justify-center px-8 py-4 text-base font-bold text-app-text-main bg-white hover:bg-slate-50 rounded-xl shadow-xl transition-transform hover:scale-105 active:scale-95">
              Start your first project
              <ArrowRight className="ml-2 h-5 w-5" />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
};

export default HowItWorks;

