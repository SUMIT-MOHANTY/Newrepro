import { ArrowRight, CheckCircle, Workflow, FileText, BrainCircuit, GaugeCircle, Shield, Sparkles } from 'lucide-react';
import Logo from '../assets/logo.png';
import { Link } from 'react-router-dom';

const steps = [
  {
    title: 'Upload your BRD',
    description:
      'Securely upload BRDs, SRS, proposals, or other requirement documents in popular formats like PDF, DOCX, PPTX, or text. For example: a 40-page “Retail Mobile App BRD” straight from your BA team.',
    icon: FileText,
    badge: 'Step 1',
  },
  {
    title: 'AI parses & understands context',
    description:
      'Our AI engine reads every section, identifies modules, integrations, constraints, and non-functional requirements, then builds an internal project model. It understands things like “Customer Onboarding”, “Order Management”, and “Notifications” as separate building blocks.',
    icon: BrainCircuit,
    badge: 'Step 2',
  },
  {
    title: 'Insights & technical breakdown',
    description:
      'You get structured outputs including feasibility, risks, architecture suggestions, backlog candidates, and questions to clarify with stakeholders. For the mobile app BRD, this might become 6–8 epics, clear integration points (payments, CRM, SMS), and a list of open questions.',
    icon: Workflow,
    badge: 'Step 3',
  },
  {
    title: 'Track & refine over time',
    description:
      'Iterate with updated documents and track versions so your technical view of the project always stays in sync with the latest BRD. When scope changes (“add loyalty program”), you upload the new version and instantly see what it impacts.',
    icon: GaugeCircle,
    badge: 'Step 4',
  },
];

const valuePoints = [
  {
    title: 'From raw docs to ready insights',
    description:
      'Skip manual reading marathons. DSuite converts long, unstructured requirement docs into a concise, navigable view that your team can act on immediately.',
  },
  {
    title: 'Aligned with enterprise delivery',
    description:
      'Outputs are structured around how real delivery teams work: modules, epics, dependencies, risks, and questions you can take straight into planning.',
  },
  {
    title: 'Built for repeatable governance',
    description:
      'Governance scoring and contextual checks help you compare projects, enforce standards, and avoid surprises late in the lifecycle.',
  },
];

const faqs = [
  {
    q: 'What types of documents does DSuite support?',
    a: 'You can start with BRDs, SRS documents, proposals, RFP responses, or any structured requirement document. We support common formats like PDF, DOCX, PPTX, and text.',
  },
  {
    q: 'Will DSuite change the way we write BRDs?',
    a: 'No. DSuite is designed to work with the documents you already create today. Better-structured docs will yield even richer analysis, but we do not force a new template.',
  },
  {
    q: 'Is my data secure?',
    a: 'Yes. Documents are processed in a secure environment with strict access controls. You retain ownership of your data and outputs.',
  },
  {
    q: 'Do I need technical knowledge to use DSuite?',
    a: 'Business analysts, architects, and delivery leads can all use DSuite. The interface is simple, while the outputs are detailed enough for technical teams.',
  },
];

const HowItWorks = () => {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans">
      {/* Top nav – consistent with landing but simple */}
      <nav className="w-full bg-white/90 backdrop-blur-md z-40 border-b border-slate-100 sticky top-0">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="flex items-center gap-3">
              <img src={Logo} alt="DSuite" className="h-9 w-auto" />
              <div className="h-6 w-px bg-slate-200" />
              <span className="text-lg font-bold tracking-tight text-slate-900">
                DSuite
              </span>
            </Link>
            <div className="flex items-center gap-3">
              <Link
                to="/"
                className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
              >
                Back to home
              </Link>
              <Link
                to="/login"
                className="hidden sm:inline-flex text-sm font-semibold text-slate-700 px-3 py-1.5 rounded-lg hover:bg-slate-50 border border-slate-200 transition-colors"
              >
                Log in
              </Link>
              <Link
                to="/signup"
                className="inline-flex items-center text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg shadow-sm shadow-blue-500/30 transition-colors"
              >
                Get started
                <ArrowRight className="ml-1.5 h-4 w-4" />
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-10 pb-10 sm:pt-14 sm:pb-14 lg:pt-16 lg:pb-16 px-4 sm:px-6 lg:px-8 bg-gradient-to-b from-white via-slate-50 to-slate-100 border-b border-slate-100">
        <div className="max-w-6xl mx-auto grid lg:grid-cols-[1.4fr,1fr] gap-10 lg:gap-14 items-center">
          <div className="space-y-5 sm:space-y-6">
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-blue-50 border border-blue-100 rounded-full text-blue-600 text-xs font-semibold">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
              </span>
              How DSuite works
            </div>
            <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-slate-900">
              From{' '}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600">
                document
              </span>{' '}
              to decision in minutes.
            </h1>
            <p className="text-base sm:text-lg text-slate-600 max-w-xl">
              DSuite turns long requirement documents into structured, technical insight so your teams can
              validate feasibility, align architecture, and plan delivery without days of manual reading.
            </p>
            <div className="flex flex-wrap gap-3 text-sm text-slate-600">
              <div className="inline-flex items-center gap-1.5">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span>No change to your current BRD templates</span>
              </div>
              <div className="inline-flex items-center gap-1.5">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span>Designed for enterprise governance</span>
              </div>
            </div>
          </div>

          <div className="relative">
            <div className="absolute -inset-4 bg-gradient-to-tr from-blue-100/70 via-indigo-100/60 to-slate-50 rounded-3xl blur-2xl opacity-70" />
            <div className="relative bg-white border border-slate-200 rounded-2xl shadow-xl overflow-hidden">
              <div className="p-5 border-b border-slate-100 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center">
                    <Sparkles className="h-4 w-4 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-slate-500">Sample BRD</p>
                    <p className="text-sm font-semibold text-slate-900">E-commerce Platform Revamp</p>
                  </div>
                </div>
                <span className="text-[11px] font-semibold text-green-600 bg-green-50 border border-green-100 px-2 py-0.5 rounded-full">
                  Analyzed
                </span>
              </div>
              <div className="p-5 space-y-4 bg-slate-50/60">
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="bg-white border border-slate-100 rounded-xl p-3 space-y-1">
                    <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
                      Feasibility
                    </p>
                    <p className="text-sm font-semibold text-emerald-600">Viable with minor risks</p>
                    <p className="text-[11px] text-slate-500">
                      2 integration risks identified, 1 scope clarification.
                    </p>
                  </div>
                  <div className="bg-white border border-slate-100 rounded-xl p-3 space-y-1">
                    <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
                      Architecture
                    </p>
                    <p className="text-sm font-semibold text-slate-800">Suggested microservice design</p>
                    <p className="text-[11px] text-slate-500">
                      Recommends API gateway, notification service, and reporting module.
                    </p>
                  </div>
                </div>
                <div className="bg-white border border-slate-100 rounded-xl p-3 space-y-2">
                  <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
                    Questions to clarify with stakeholders
                  </p>
                  <ul className="space-y-1">
                    <li className="flex gap-2 text-[11px] text-slate-600">
                      <span className="mt-[6px] h-1.5 w-1.5 rounded-full bg-blue-500 flex-shrink-0" />
                      <span>Payment provider SLAs and reconciliation requirements.</span>
                    </li>
                    <li className="flex gap-2 text-[11px] text-slate-600">
                      <span className="mt-[6px] h-1.5 w-1.5 rounded-full bg-blue-500 flex-shrink-0" />
                      <span>Expected traffic spikes during campaigns.</span>
                    </li>
                    <li className="flex gap-2 text-[11px] text-slate-600">
                      <span className="mt-[6px] h-1.5 w-1.5 rounded-full bg-blue-500 flex-shrink-0" />
                      <span>Compliance and data residency constraints.</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Steps section */}
      <section className="py-14 sm:py-16 lg:py-20 bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-3xl mb-10">
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 mb-3">
              How DSuite fits into your delivery flow
            </h2>
            <p className="text-slate-600 text-sm sm:text-base">
              DSuite is designed to sit between requirements and execution, giving teams a shared,
              technical view of what&apos;s being asked before estimates, architecture, and planning
              begin.
            </p>
          </div>
          <div className="grid md:grid-cols-2 gap-6 lg:gap-8">
            {steps.map((step, index) => {
              const Icon = step.icon;
              return (
                <div
                  key={step.title}
                  className="relative bg-slate-50 border border-slate-100 rounded-2xl p-5 sm:p-6 hover:border-blue-200 hover:shadow-sm transition-colors"
                >
                  <div className="flex items-start gap-4">
                    <div className="flex flex-col items-center">
                      <div className="h-10 w-10 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-md shadow-blue-500/30">
                        <Icon className="h-5 w-5" />
                      </div>
                      {index < steps.length - 1 && (
                        <div className="mt-2 w-px flex-1 bg-gradient-to-b from-blue-200 via-slate-200 to-transparent hidden sm:block" />
                      )}
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-blue-50 text-blue-600 border border-blue-100">
                          {step.badge}
                        </span>
                      </div>
                      <h3 className="text-base sm:text-lg font-semibold text-slate-900">
                        {step.title}
                      </h3>
                      <p className="text-sm text-slate-600 leading-relaxed">{step.description}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Concrete example section */}
      <section className="py-10 sm:py-12 lg:py-16 bg-slate-50 border-t border-slate-100">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-3xl mb-6">
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 mb-2">
              See it with a real project example
            </h2>
            <p className="text-sm sm:text-base text-slate-600">
              Here&apos;s what DSuite would do with a typical &quot;Online Loan Origination System BRD&quot;.
            </p>
          </div>
          <div className="grid md:grid-cols-2 gap-6 items-start">
            <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6 shadow-sm">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                Input from your side
              </p>
              <ul className="space-y-2 text-sm text-slate-600">
                <li>• 55-page BRD covering customer onboarding, KYC, scoring, and disbursement.</li>
                <li>• High-level non-functional section with performance and availability targets.</li>
                <li>• A few scattered notes about integrations (CBS, bureau, SMS gateway).</li>
              </ul>
            </div>
            <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6 shadow-sm">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                What DSuite gives back
              </p>
              <ul className="space-y-2 text-sm text-slate-600">
                <li>• A project map split into modules like &quot;Onboarding&quot;, &quot;Decisioning&quot;, &quot;Servicing&quot;.</li>
                <li>• Feasibility summary with key risks (e.g. missing SLA details for CBS, unclear batch vs. real-time flows).</li>
                <li>• Suggested architecture options and integration points for each external system.</li>
                <li>• A list of concrete clarification questions you can send back to business and architecture teams.</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Value section */}
      <section className="py-12 sm:py-16 lg:py-18 bg-slate-900 text-white relative overflow-hidden">
        <div className="absolute inset-0 opacity-20 mix-blend-overlay bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.2),_transparent_60%),radial-gradient(circle_at_bottom,_rgba(129,140,248,0.25),_transparent_55%)]" />
        <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-3xl mb-10">
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight mb-3">
              Why teams use DSuite before writing a single line of code
            </h2>
            <p className="text-sm sm:text-base text-slate-200">
              Whether you&apos;re a delivery lead, architect, or BA, DSuite helps you see the project
              the way engineering will, from day one.
            </p>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            {valuePoints.map((point) => (
              <div
                key={point.title}
                className="bg-white/5 border border-white/10 rounded-2xl p-5 sm:p-6 backdrop-blur-sm"
              >
                <h3 className="text-base sm:text-lg font-semibold mb-2">{point.title}</h3>
                <p className="text-sm text-slate-200 leading-relaxed">{point.description}</p>
              </div>
            ))}
          </div>

          <div className="mt-10 flex flex-wrap gap-3 text-xs sm:text-sm text-slate-200">
            <div className="inline-flex items-center gap-1.5">
              <Shield className="h-4 w-4 text-emerald-400" />
              <span>Secure document handling</span>
            </div>
            <div className="inline-flex items-center gap-1.5">
              <Workflow className="h-4 w-4 text-sky-300" />
              <span>Governance-ready outputs</span>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="py-14 sm:py-16 lg:py-20 bg-white">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-8">
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 mb-2">
              Frequently asked questions
            </h2>
            <p className="text-sm sm:text-base text-slate-600">
              A quick overview of how DSuite behaves in real-world projects.
            </p>
          </div>
          <div className="space-y-4">
            {faqs.map((item) => (
              <div
                key={item.q}
                className="border border-slate-200 rounded-xl p-4 sm:p-5 bg-slate-50/60 hover:border-blue-200 transition-colors"
              >
                <h3 className="text-sm sm:text-base font-semibold text-slate-900 mb-1.5">
                  {item.q}
                </h3>
                <p className="text-sm text-slate-600 leading-relaxed">{item.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-12 sm:py-16 bg-slate-50 border-t border-slate-200">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-2xl sm:text-3xl font-bold text-slate-900 mb-3">
            Ready to see your BRDs the way engineers do?
          </h2>
          <p className="text-sm sm:text-base text-slate-600 max-w-2xl mx-auto mb-6">
            Start with a single document, get a complete technical breakdown, and share it with your
            delivery and architecture teams in minutes.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              to="/signup"
              className="inline-flex items-center justify-center px-7 py-3 text-sm sm:text-base font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-xl shadow-lg shadow-blue-500/30 transition-colors"
            >
              Start analysis free
              <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
            <Link
              to="/login"
              className="inline-flex items-center justify-center px-7 py-3 text-sm sm:text-base font-semibold text-slate-800 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors"
            >
              Log in to DSuite
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
};

export default HowItWorks;

