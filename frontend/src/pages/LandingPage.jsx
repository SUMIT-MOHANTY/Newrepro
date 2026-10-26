import { useEffect, useState, useCallback } from 'react';

export default function LandingPage() {
    const [theme, setTheme] = useState(localStorage.getItem('theme') || 'dark');
    const [showReleaseNotes, setShowReleaseNotes] = useState(false);

    useEffect(() => {
        // Apply theme to document element
        const applyTheme = (t) => {
            if (t === 'dark') {
                document.documentElement.classList.add('dark');
                document.documentElement.setAttribute('data-theme', 'dark');
            } else {
                document.documentElement.classList.remove('dark');
                document.documentElement.setAttribute('data-theme', 'light');
            }
        };

        applyTheme(theme);

        const handleThemeChange = () => {
            const currentTheme = localStorage.getItem('theme') || 'dark';
            setTheme(currentTheme);
            applyTheme(currentTheme);
            setTimeout(updateFooter, 50);
        };

        window.addEventListener('theme-changed', handleThemeChange);
        
        // Listen for release notes open event from navbar button
        const handleOpenReleaseNotes = () => setShowReleaseNotes(true);
        window.addEventListener('open-release-notes', handleOpenReleaseNotes);

        // 1. Inject the new landing page stylesheet
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = '/assets/index-DZGiql0S.css';
        link.id = 'landing-page-css';
        document.head.appendChild(link);

        // 2. Inject the new landing page JS bundle
        const script = document.createElement('script');
        script.type = 'module';
        script.src = '/assets/index-DabgM5Gx.js';
        script.id = 'landing-page-js';
        document.body.appendChild(script);

        // 3. Dynamic Navbar Button Injections (Docs, Flyer, Release Notes & Theme Toggle)
        const injectNavbarButtons = () => {
            const existingDocsBtn = document.getElementById('docs-nav-button');
            const existingFlyerBtn = document.getElementById('flyer-nav-button');
            const existingReleaseBtn = document.getElementById('release-notes-nav-button');
            const existingThemeBtn = document.getElementById('theme-nav-button');
            
            if (existingDocsBtn && existingFlyerBtn && existingReleaseBtn && existingThemeBtn) return; // Already injected
            
            const allElements = Array.from(document.querySelectorAll('a, button, div, span'));
            const workflowElement = allElements.find(el => el.textContent?.trim() === 'Workflow');
            const featuresElement = allElements.find(el => el.textContent?.trim() === 'Features');
            const anchorElement = workflowElement || featuresElement;
            
            if (anchorElement) {
                const parent = anchorElement.parentNode;
                
                // Create Docs Button if not existing
                if (!existingDocsBtn) {
                    const docsButton = anchorElement.cloneNode(true);
                    docsButton.id = 'docs-nav-button';
                    docsButton.textContent = 'Docs';
                    docsButton.innerHTML = 'Docs';
                    
                    if (docsButton.tagName === 'A') {
                        docsButton.href = '/docs';
                    } else {
                        docsButton.style.cursor = 'pointer';
                        docsButton.onclick = (e) => {
                            e.preventDefault();
                            window.location.href = '/docs';
                        };
                    }
                    
                    if (anchorElement.nextSibling) {
                        parent.insertBefore(docsButton, anchorElement.nextSibling);
                    } else {
                        parent.appendChild(docsButton);
                    }
                }

                // Create Flyer Button if not existing
                if (!existingFlyerBtn) {
                    const docsBtnRef = document.getElementById('docs-nav-button') || anchorElement;
                    const flyerButton = anchorElement.cloneNode(true);
                    flyerButton.id = 'flyer-nav-button';
                    flyerButton.textContent = 'Brochure';
                    flyerButton.innerHTML = 'Brochure';
                    
                    if (flyerButton.tagName === 'A') {
                        flyerButton.href = '/Dsuite_Brochure.pdf';
                        flyerButton.download = 'Dsuite_Brochure.pdf';
                    } else {
                        flyerButton.style.cursor = 'pointer';
                        flyerButton.onclick = (e) => {
                            e.preventDefault();
                            const link = document.createElement('a');
                            link.href = '/Dsuite_Brochure.pdf';
                            link.download = 'Dsuite_Brochure.pdf';
                            document.body.appendChild(link);
                            link.click();
                            document.body.removeChild(link);
                        };
                    }
                    
                    if (docsBtnRef.nextSibling) {
                        parent.insertBefore(flyerButton, docsBtnRef.nextSibling);
                    } else {
                        parent.appendChild(flyerButton);
                    }
                }

                // Create Release Notes Button if not existing
                if (!existingReleaseBtn) {
                    const flyerBtnRef = document.getElementById('flyer-nav-button') || document.getElementById('docs-nav-button') || anchorElement;
                    const releaseButton = anchorElement.cloneNode(true);
                    releaseButton.id = 'release-notes-nav-button';
                    releaseButton.textContent = 'Release Notes';
                    releaseButton.innerHTML = 'Release Notes';
                    releaseButton.style.cursor = 'pointer';
                    releaseButton.onclick = (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        window.dispatchEvent(new Event('open-release-notes'));
                    };
                    if (flyerBtnRef.nextSibling) {
                        parent.insertBefore(releaseButton, flyerBtnRef.nextSibling);
                    } else {
                        parent.appendChild(releaseButton);
                    }
                }

                // Create Theme Toggle Button if not existing
                const currentFlyerBtn = document.getElementById('release-notes-nav-button') || document.getElementById('flyer-nav-button') || document.getElementById('docs-nav-button') || anchorElement;
                if (!existingThemeBtn) {
                    const themeButton = document.createElement('button');
                    themeButton.id = 'theme-nav-button';
                    
                    // Match landing page link classes and styles
                    themeButton.className = 'bourntec-nav-link';
                    themeButton.style.cursor = 'pointer';
                    themeButton.style.display = 'inline-flex';
                    themeButton.style.alignItems = 'center';
                    themeButton.style.justifyContent = 'center';
                    themeButton.style.padding = '4px 8px';
                    themeButton.style.marginLeft = '12px';
                    themeButton.style.border = 'none';
                    themeButton.style.backgroundColor = 'transparent';
                    
                    // Render sun/moon path dynamically based on theme
                    const currentTheme = localStorage.getItem('theme') || 'dark';
                    const isDark = currentTheme === 'dark';
                    themeButton.innerHTML = isDark 
                        ? `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-sun"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>`
                        : `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-moon"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>`;
                    
                    themeButton.onclick = (e) => {
                        e.preventDefault();
                        const t = localStorage.getItem('theme') || 'dark';
                        const newTheme = t === 'dark' ? 'light' : 'dark';
                        localStorage.setItem('theme', newTheme);
                        applyTheme(newTheme);
                        setTheme(newTheme);
                        
                        // Update button icon
                        themeButton.innerHTML = newTheme === 'dark'
                            ? `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-sun"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>`
                            : `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-moon"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>`;
                        
                        // Broadcast change to other pages
                        window.dispatchEvent(new Event('theme-changed'));
 
                        // Update branding and logos for new theme
                        setTimeout(() => {
                            const logo = document.getElementById('bourntec-landing-logo');
                            if (logo) {
                                logo.src = '/assets/docs/dsuite_logo.png';
                            }
                            rebrandLandingLogos();
                            injectBourntecNavLogo();
                            updateFooter();
                        }, 50);
                    };
                    
                    if (currentFlyerBtn.nextSibling) {
                        parent.insertBefore(themeButton, currentFlyerBtn.nextSibling);
                    } else {
                        parent.appendChild(themeButton);
                    }
                }
            }
        };

        // 3b. Inject Bourntec logo on the right side of desktop navbar
        const injectBourntecNavLogo = () => {
            const currentTheme = localStorage.getItem('theme') || 'dark';
            const isDark = currentTheme === 'dark';
            const bourntecLogoSrc = isDark ? '/assets/docs/bourntec_logo.png' : '/assets/docs/bourntec_logo_l.png';
            
            let bourntecContainer = document.getElementById('bourntec-nav-right-container');
            if (bourntecContainer) {
                const img = bourntecContainer.querySelector('img');
                if (img) img.src = bourntecLogoSrc;
                bourntecContainer.style.borderLeft = isDark ? '1px solid rgba(255, 255, 255, 0.15)' : '1px solid rgba(0, 0, 0, 0.12)';
                return;
            }

            const desktopMenu = document.querySelector('.desktop-menu');
            if (desktopMenu) {
                bourntecContainer = document.createElement('div');
                bourntecContainer.id = 'bourntec-nav-right-container';
                bourntecContainer.style.display = 'inline-flex';
                bourntecContainer.style.alignItems = 'center';
                bourntecContainer.style.marginLeft = '12px';
                bourntecContainer.style.paddingLeft = '16px';
                bourntecContainer.style.borderLeft = isDark ? '1px solid rgba(255, 255, 255, 0.15)' : '1px solid rgba(0, 0, 0, 0.12)';

                const link = document.createElement('a');
                link.href = 'https://www.bourntec.com/';
                link.target = '_blank';
                link.rel = 'noopener noreferrer';
                link.title = 'Bourntec Solutions';
                link.style.display = 'inline-flex';
                link.style.alignItems = 'center';
                link.style.textDecoration = 'none';

                const img = document.createElement('img');
                img.id = 'bourntec-nav-right-logo';
                img.src = bourntecLogoSrc;
                img.alt = 'Bourntec Solutions';
                img.style.height = '24px';
                img.style.width = 'auto';
                img.style.display = 'block';
                img.style.opacity = '0.9';
                img.style.transition = 'opacity 0.2s';
                img.onmouseenter = () => { img.style.opacity = '1'; };
                img.onmouseleave = () => { img.style.opacity = '0.9'; };

                link.appendChild(img);
                bourntecContainer.appendChild(link);
                desktopMenu.appendChild(bourntecContainer);
            }
        };

        // 3c. Replace DSuite branding with Ribbon Logo + tight .Pro text in electric sky-cyan
        const rebrandLandingLogos = () => {
            const currentTheme = localStorage.getItem('theme') || 'dark';
            const isDark = currentTheme === 'dark';
            const logoSrc = isDark ? '/assets/docs/dsuite_logo_white.png' : '/assets/docs/dsuite_logo.png';
            const proGradient = isDark 
                ? 'linear-gradient(135deg, #38bdf8 0%, #22d3ee 100%)' 
                : 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)';

            // Replace sparkles icon + "DSuite" gradient text in desktop-menu navbar
            const gradientTextEls = document.querySelectorAll('.gradient-text');
            gradientTextEls.forEach(el => {
                if (el.textContent.trim() === 'DSuite' || el.textContent.trim() === '.Pro') {
                    // Skip if this is inside our wrapper or footer
                    if (el.id === 'bourntec-landing-label' || el.closest('#bourntec-landing-logo-wrapper') || el.closest('footer')) {
                        return;
                    }
                    const parent = el.parentNode;
                    // Remove the sparkles icon box (previous sibling div with gradient bg)
                    const iconBox = parent.querySelector('div[style*="gradient"]');
                    if (iconBox && iconBox !== el) {
                        iconBox.remove();
                    }
                    // Create wrapper with logo image + .Pro text
                    const wrapper = document.createElement('div');
                    wrapper.style.display = 'flex';
                    wrapper.style.alignItems = 'center';
                    wrapper.style.gap = '0px';
                    wrapper.id = 'bourntec-landing-logo-wrapper';
                    wrapper.style.cursor = 'pointer';
                    wrapper.onclick = () => { window.location.href = '/'; };

                    const img = document.createElement('img');
                    img.src = logoSrc;
                    img.alt = 'DSuite.Pro';
                    img.style.height = '32px';
                    img.style.width = 'auto';
                    img.style.display = 'block';
                    img.id = 'bourntec-landing-logo';
                    img.style.transform = 'translateY(-1px)';

                    const label = document.createElement('span');
                    label.textContent = '.Pro';
                    label.className = 'dsuite-pro-brand-label';
                    label.id = 'bourntec-landing-label';
                    label.style.lineHeight = '1';
                    label.style.alignSelf = 'center';
                    label.style.transform = 'translateY(1px)';
                    label.style.display = 'inline-block';
                    label.style.fontSize = '20px';
                    label.style.fontWeight = '800';
                    label.style.letterSpacing = '-0.02em';
                    label.style.marginLeft = '-2px';
                    label.style.background = proGradient;
                    label.style.webkitBackgroundClip = 'text';
                    label.style.webkitTextFillColor = 'transparent';

                    wrapper.appendChild(img);
                    wrapper.appendChild(label);
                    el.replaceWith(wrapper);
                }
            });

            // Also update existing logo and label if theme changed
            const existingLogo = document.getElementById('bourntec-landing-logo');
            if (existingLogo) {
                existingLogo.src = logoSrc;
            }
            const existingLabel = document.getElementById('bourntec-landing-label');
            if (existingLabel) {
                existingLabel.textContent = '.Pro';
                existingLabel.style.marginLeft = '-2px';
                existingLabel.style.background = proGradient;
                existingLabel.style.webkitBackgroundClip = 'text';
                existingLabel.style.webkitTextFillColor = 'transparent';
            }
        };

        const updateVibeCodingButton = () => {
            const spans = Array.from(document.querySelectorAll('span, button, a'));
            const badge = spans.find(el => {
                const txt = (el.textContent || '').trim();
                const isBadge = el.style.borderRadius === '9999px' || el.style.display === 'inline-flex' || el.style.padding === '4px 12px';
                return (txt === 'Vibe Coding Mode' || txt === 'Launch Vibe Coding \u2197') && isBadge;
            });
            if (badge) {
                badge.style.cursor = 'pointer';
                badge.style.userSelect = 'none';
                badge.onclick = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    window.open('https://sandbox1-dsuite.bourntec.com/vibecoding/', '_blank');
                };
                badge.textContent = 'Launch Vibe Coding \u2197';
                badge.style.background = 'linear-gradient(90deg, #ec4899, #db2777)';
                badge.style.color = '#ffffff';
                badge.style.textDecoration = 'none';
                badge.style.transition = 'all 0.2s ease';
                badge.style.boxShadow = '0 0 12px rgba(236, 72, 153, 0.4)';
                badge.onmouseenter = () => {
                    badge.style.opacity = '0.9';
                    badge.style.transform = 'scale(1.05)';
                    badge.style.textDecoration = 'underline';
                    badge.style.boxShadow = '0 0 16px rgba(236, 72, 153, 0.6)';
                };
                badge.onmouseleave = () => {
                    badge.style.opacity = '1';
                    badge.style.transform = 'scale(1)';
                    badge.style.textDecoration = 'none';
                    badge.style.boxShadow = '0 0 12px rgba(236, 72, 153, 0.4)';
                };
            }
            // Revert any accidental modifications to non-badge subtitle text
            spans.forEach(el => {
                const txt = (el.textContent || '').trim();
                const isBadge = el.style.borderRadius === '9999px' || el.style.display === 'inline-flex' || el.style.padding === '4px 12px';
                if (txt === 'Launch Vibe Coding \u2197' && !isBadge) {
                    el.textContent = 'Vibe Coding Mode';
                    el.style.cursor = '';
                    el.onclick = null;
                }
            });
        };

        const updateFooter = () => {
            const footer = document.querySelector('footer');
            if (!footer) return;

            // 1. Update copyright text
            const pElements = Array.from(footer.querySelectorAll('p'));
            const copyrightText = pElements.find(p => p.textContent.includes('2024') || p.textContent.includes('DSuite'));
            if (copyrightText && copyrightText.textContent.includes('2024')) {
                copyrightText.innerHTML = copyrightText.innerHTML.replace('2024', '2026');
            }

            // 2. Update links hrefs
            const links = Array.from(footer.querySelectorAll('a'));
            links.forEach(link => {
                const text = link.textContent.trim();
                if (text === 'Features') {
                    link.href = '#features';
                } else if (text === 'Pricing') {
                    link.href = '/login';
                } else if (text === 'Documentation') {
                    link.href = '/docs';
                } else if (text === 'API Reference') {
                    link.href = '/docs';
                } else if (text === 'About') {
                    link.href = 'https://www.bourntec.com/about-us/';
                    link.target = '_blank';
                } else if (text === 'Blog') {
                    link.href = 'https://www.bourntec.com/blog/';
                    link.target = '_blank';
                } else if (text === 'Careers') {
                    link.href = 'https://www.bourntec.com/careers/';
                    link.target = '_blank';
                } else if (text === 'Contact') {
                    link.href = 'https://www.bourntec.com/contact-us/';
                    link.target = '_blank';
                } else if (text === 'Privacy') {
                    link.href = 'https://www.bourntec.com/privacy-policy/';
                    link.target = '_blank';
                } else if (text === 'Terms') {
                    link.href = 'https://www.bourntec.com/terms-of-use/';
                    link.target = '_blank';
                } else if (text === 'Security') {
                    link.href = '/docs';
                } else if (text === 'Compliance') {
                    link.href = '/docs';
                }
            });

            // 3. Rebrand DSuite logo in footer with Ribbon Logo + .Pro
            const currentTheme = localStorage.getItem('theme') || 'dark';
            const isDark = currentTheme === 'dark';
            const proGradient = isDark 
                ? 'linear-gradient(135deg, #38bdf8 0%, #22d3ee 100%)' 
                : 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)';

            const spans = Array.from(footer.querySelectorAll('span'));
            const brandSpan = spans.find(span => (span.textContent.trim() === 'DSuite' || span.textContent.trim() === '.Pro') && (span.className.includes('gradient-text') || span.id === 'bourntec-footer-label'));
            if (brandSpan) {
                brandSpan.textContent = '.Pro';
                brandSpan.id = 'bourntec-footer-label';
                brandSpan.style.marginLeft = '-2px';
                brandSpan.style.fontSize = '20px';
                brandSpan.style.fontWeight = '800';
                brandSpan.style.letterSpacing = '-0.02em';
                brandSpan.style.background = proGradient;
                brandSpan.style.webkitBackgroundClip = 'text';
                brandSpan.style.webkitTextFillColor = 'transparent';

                if (!document.getElementById('bourntec-footer-logo')) {
                    const parent = brandSpan.parentNode;
                    const iconDiv = parent.querySelector('div[style*="width: 40px"]');
                    if (iconDiv) {
                        iconDiv.remove();
                    }
                    
                    const logoSrc = isDark ? '/assets/docs/dsuite_logo_white.png' : '/assets/docs/dsuite_logo.png';

                    const img = document.createElement('img');
                    img.src = logoSrc;
                    img.alt = 'DSuite.Pro Logo';
                    img.id = 'bourntec-footer-logo';
                    img.style.height = '36px';
                    img.style.width = 'auto';
                    img.style.marginRight = '0px';
                    img.style.display = 'block';

                    parent.insertBefore(img, brandSpan);
                } else {
                    const logoSrc = isDark ? '/assets/docs/dsuite_logo_white.png' : '/assets/docs/dsuite_logo.png';
                    const img = document.getElementById('bourntec-footer-logo');
                    if (img) img.src = logoSrc;
                }
            }
        };

        // Try to inject multiple times to account for compiled script rendering delays
        const delays = [100, 300, 500, 1000, 1500, 2000, 3000];
        const timeouts = delays.map(delay => setTimeout(() => {
            injectNavbarButtons();
            injectBourntecNavLogo();
            rebrandLandingLogos();
            updateVibeCodingButton();
            updateFooter();
        }, delay));

        // 4. Intercept click events on CTA buttons
        const handleGlobalClick = (e) => {
            // Update button when anything is clicked (mode switch)
            setTimeout(updateVibeCodingButton, 50);

            const target = e.target.closest('button, a');
            if (!target) return;
            
            const text = (target.textContent || '').trim().toLowerCase();
            
            if (
                text === 'get started' || 
                text === 'get started free' || 
                text === 'launch compiled application' || 
                text === 'schedule demo'
            ) {
                e.preventDefault();
                e.stopPropagation();
                window.location.href = '/login';
            }
            
            if (
                text.includes('documentation') ||
                text.includes('learn more') ||
                text.includes('docs') ||
                text.includes('user guide')
            ) {
                e.preventDefault();
                e.stopPropagation();
                window.location.href = '/docs';
            }
        };

        document.addEventListener('click', handleGlobalClick, true);

        return () => {
            timeouts.forEach(clearTimeout);
            window.removeEventListener('theme-changed', handleThemeChange);
            window.removeEventListener('open-release-notes', handleOpenReleaseNotes);
            
            const existingLink = document.getElementById('landing-page-css');
            if (existingLink) existingLink.remove();

            const existingScript = document.getElementById('landing-page-js');
            if (existingScript) existingScript.remove();
            
            const docsBtn = document.getElementById('docs-nav-button');
            if (docsBtn) docsBtn.remove();

            const flyerBtn = document.getElementById('flyer-nav-button');
            if (flyerBtn) flyerBtn.remove();
            
            const releaseBtn = document.getElementById('release-notes-nav-button');
            if (releaseBtn) releaseBtn.remove();
            
            const themeBtn = document.getElementById('theme-nav-button');
            if (themeBtn) themeBtn.remove();

            document.removeEventListener('click', handleGlobalClick, true);
        };
    }, []);

    return (
        <>
            <div id="landing-root"></div>
            
            {/* Scoped CSS overrides for the landing page light theme inline styles */}
            <style dangerouslySetInnerHTML={{__html: `
                /* Hide AI-Powered Development Platform badge */
                .hero-badge {
                    display: none !important;
                }

                /* Add top gap to hero title since badge is hidden */
                .hero-title {
                    margin-top: 2rem !important;
                }

                /* Tour Viewport Height Alignment Override (Globally for both Dark & Light themes) */
                .tour-viewport {
                    min-height: 550px !important;
                    max-height: 550px !important;
                }
                
                [data-theme=light] .bourntec-landing {
                    background: #fafbfc !important;
                    color: #18181b !important;
                }
                [data-theme=light] .bourntec-landing:before {
                    background: radial-gradient(circle at 50% 30%, rgba(124, 58, 237, 0.08) 0%, rgba(99, 102, 241, 0.03) 50%, transparent 100%) !important;
                }
                [data-theme=light] .bourntec-nav {
                    background: rgba(250, 251, 252, 0.8) !important;
                    border-bottom: 1px solid #e4e4e7 !important;
                }
                [data-theme=light] .bourntec-nav-link {
                    color: #52525b !important;
                }
                [data-theme=light] .bourntec-nav-link:hover {
                    color: #18181b !important;
                }
                [data-theme=light] .bourntec-footer {
                    background: #fafbfc !important;
                    border-top: 1px solid #e4e4e7 !important;
                }
                [data-theme=light] .bourntec-hero-title span {
                    background: linear-gradient(135deg, #7c3aed 0%, #db2777 100%) !important;
                    -webkit-text-fill-color: transparent !important;
                    -webkit-background-clip: text !important;
                }
                [data-theme=light] .bourntec-hero-desc {
                    color: #52525b !important;
                }
                
                /* Multi-agent Loop Panel Showcase (first screenshot) */
                [data-theme=light] #landing-root div[style*="height: 700px"] {
                    background: #ffffff !important;
                    border: 1px solid #e4e4e7 !important;
                    box-shadow: 0 25px 50px rgba(0, 0, 0, 0.04) !important;
                }
                [data-theme=light] #landing-root div[style*="height: 700px"] h3 {
                    color: #18181b !important;
                }
                [data-theme=light] #landing-root div[style*="height: 700px"] p {
                    color: #52525b !important;
                }
                [data-theme=light] #landing-root div[style*="background: rgba(10, 10, 15, 0.9)"],
                [data-theme=light] #landing-root div[style*="rgba(10,10,15,0.9)"] {
                    background: #ffffff !important;
                    border: 1px solid #e2e8f0 !important;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05) !important;
                }
                [data-theme=light] #landing-root div[style*="rgba(10,10,15,0.9)"] p {
                    color: #334155 !important;
                }
                [data-theme=light] #landing-root div[style*="rgba(10,10,15,0.9)"] span {
                    color: #64748b !important;
                }
                [data-theme=light] #landing-root div[style*="rgba(10,10,15,0.9)"] div {
                    background: #f8fafc !important;
                    border: 1px solid #e2e8f0 !important;
                    color: #1e293b !important;
                }
                [data-theme=light] #landing-root div[style*="background: rgba(100, 100, 120, 0.8)"],
                [data-theme=light] #landing-root div[style*="rgba(100,100,120,0.8)"] {
                    background: #f1f5f9 !important;
                    border: 1px solid #cbd5e1 !important;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.03) !important;
                }
                [data-theme=light] #landing-root div[style*="rgba(100,100,120,0.8)"] button {
                    color: #475569 !important;
                }
                
                /* Explore Steps Tour (second screenshot) */
                [data-theme=light] section[id="tour"] {
                    background: #f8fafc !important;
                }
                [data-theme=light] .tour-step-btn {
                    color: #52525b !important;
                }
                [data-theme=light] .tour-step-btn:hover {
                    background: #f4f4f5 !important;
                    border-color: #e4e4e7 !important;
                }
                [data-theme=light] .tour-step-btn.active {
                    background: #ffffff !important;
                    border-color: rgba(124, 58, 237, 0.15) !important;
                    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.04) !important;
                }
                [data-theme=light] .tour-step-title {
                    color: #52525b !important;
                }
                [data-theme=light] .tour-step-btn.active .tour-step-title {
                    color: #18181b !important;
                }
                [data-theme=light] .tour-step-icon-wrapper {
                    background: #f4f4f5 !important;
                    border: 1px solid #e4e4e7 !important;
                    color: #71717a !important;
                }
                [data-theme=light] .tour-step-icon-wrapper.active {
                    background: linear-gradient(135deg, #7c3aed 0%, #db2777 100%) !important;
                    color: #ffffff !important;
                }
                [data-theme=light] .viewport-address {
                    background: #f4f4f5 !important;
                    border: 1px solid #e4e4e7 !important;
                    color: #71717a !important;
                }
                [data-theme=light] .autoplay-control-bar {
                    background: #f8fafc !important;
                    border: 1px solid #e4e4e7 !important;
                }
                [data-theme=light] .autoplay-control-bar button[style*="background: rgba(255, 255, 255, 0.05)"] {
                    background: #ffffff !important;
                    border-color: #cbd5e1 !important;
                    color: #64748b !important;
                }
                [data-theme=light] .autoplay-control-bar span {
                    color: #475569 !important;
                }
                
                /* Tour Viewport Container Styles */
                [data-theme=light] .tour-viewport {
                    background: #ffffff !important;
                    border: 1px solid #e4e4e7 !important;
                    box-shadow: 0 20px 45px rgba(0,0,0,0.04) !important;
                }
                [data-theme=light] .viewport-header {
                    background: #f8fafc !important;
                    border-bottom: 1px solid #e4e4e7 !important;
                }
                [data-theme=light] .tour-viewport div[style*="border-right"] {
                    border-right-color: #e4e4e7 !important;
                }
                [data-theme=light] .tour-viewport div[style*="borderRight"] {
                    border-right-color: #e4e4e7 !important;
                }
                [data-theme=light] .dropzone-mock {
                    background: #f8fafc !important;
                    border: 2px dashed #cbd5e1 !important;
                    color: #1e293b !important;
                }
                [data-theme=light] .dropzone-mock div {
                    color: #475569 !important;
                }
                [data-theme=light] .dropzone-mock div[style*="var(--text-tertiary)"] {
                    color: #64748b !important;
                }
                [data-theme=light] .dropzone-mock svg {
                    color: #7c3aed !important;
                }
                
                /* Viewport Case Flow Diagram SVG overrides (light mode colors) */
                [data-theme=light] .tour-viewport div[style*="background: rgba(9, 9, 11"],
                [data-theme=light] .tour-viewport div[style*="background:rgba(9,9,11"] {
                    background: #ffffff !important;
                    border: 1px solid #e2e8f0 !important;
                }
                [data-theme=light] .tour-viewport svg rect[fill*="indigoGrad"] {
                    fill: #f1f5f9 !important;
                    stroke: #7c3aed !important;
                }
                [data-theme=light] .tour-viewport svg rect[fill*="amberGrad"] {
                    fill: #fef3c7 !important;
                    stroke: #d97706 !important;
                }
                [data-theme=light] .tour-viewport svg rect[fill*="emeraldGrad"] {
                    fill: #d1fae5 !important;
                    stroke: #059669 !important;
                }
                [data-theme=light] .tour-viewport svg rect[fill="rgba(255, 255, 255, 0.02)"] {
                    fill: #f8fafc !important;
                    stroke: #cbd5e1 !important;
                }
                [data-theme=light] .tour-viewport svg rect[fill="rgba(59, 130, 246, 0.1)"] {
                    fill: #eff6ff !important;
                    stroke: #3b82f6 !important;
                }
                [data-theme=light] .tour-viewport svg text[fill="#f8fafc"] {
                    fill: #18181b !important;
                }
                [data-theme=light] .tour-viewport svg text[fill="#e2e8f0"] {
                    fill: #334155 !important;
                }
                [data-theme=light] .tour-viewport svg text[fill="#94a3b8"] {
                    fill: #64748b !important;
                }
                [data-theme=light] .tour-viewport svg text[fill="#fbbf24"] {
                    fill: #b45309 !important;
                }
                [data-theme=light] .tour-viewport svg text[fill="#93c5fd"] {
                    fill: #2563eb !important;
                }
                [data-theme=light] .tour-viewport svg text[fill="#c7d2fe"] {
                    fill: #4f46e5 !important;
                }
                [data-theme=light] .tour-viewport svg text[fill="#c084fc"] {
                    fill: #7e22ce !important;
                }
                [data-theme=light] .tour-viewport svg path[stroke="#475569"] {
                    stroke: #cbd5e1 !important;
                }
                [data-theme=light] .tour-viewport svg marker polygon[fill="#475569"] {
                    fill: #cbd5e1 !important;
                }
                [data-theme=light] .tour-viewport svg marker polygon[fill="#09090b"] {
                    fill: #ffffff !important;
                }
                [data-theme=light] .tour-viewport svg circle[fill="#09090b"] {
                    fill: #ffffff !important;
                }
                [data-theme=light] .tour-viewport svg marker[id="arrowhead"] polygon {
                    fill: #94a3b8 !important;
                }
                
                /* Case 3 & 4 Progress Bars and Git Consoles */
                [data-theme=light] .cortex-agent-progress-card {
                    background: #f8fafc !important;
                    border: 1px solid #e2e8f0 !important;
                }
                [data-theme=light] .cortex-agent-progress-card span {
                    color: #334155 !important;
                }
                [data-theme=light] .cortex-agent-progress-card div {
                    color: #475569 !important;
                }
                [data-theme=light] .cortex-agent-progress-card div[style*="background: rgba(255, 255, 255, 0.03)"] {
                    background: #e2e8f0 !important;
                }
                
                /* Support hex, rgb and element level overrides for console box */
                [data-theme=light] #landing-root div[style*="background: #09090d"],
                [data-theme=light] #landing-root div[style*="background:#09090d"],
                [data-theme=light] #landing-root div[style*="rgb(9, 9, 13)"],
                [data-theme=light] #landing-root div[style*="rgb(9,9,13)"],
                [data-theme=light] .tour-viewport .tour-content-panel div[style*="border-radius: 10px"],
                [data-theme=light] .tour-viewport .tour-content-panel div[style*="borderRadius: 10px"] {
                    background: #f8fafc !important;
                    border: 1px solid #cbd5e1 !important;
                    color: #1e293b !important;
                    box-shadow: none !important;
                }
                [data-theme=light] #landing-root div[style*="rgb(9, 9, 13)"] div,
                [data-theme=light] #landing-root div[style*="rgb(9,9,13)"] div,
                [data-theme=light] .tour-viewport .tour-content-panel div[style*="border-radius: 10px"] div {
                    color: #334155 !important;
                }
                [data-theme=light] #landing-root div[style*="rgb(9, 9, 13)"] div[style*="color: var(--primary-light)"],
                [data-theme=light] #landing-root div[style*="rgb(9,9,13)"] div[style*="color: var(--primary-light)"],
                [data-theme=light] .tour-viewport .tour-content-panel div[style*="border-radius: 10px"] div[style*="color: var(--primary-light)"] {
                    color: #7c3aed !important;
                }
                [data-theme=light] #landing-root div[style*="rgb(9, 9, 13)"] div[style*="color: var(--success)"],
                [data-theme=light] #landing-root div[style*="rgb(9,9,13)"] div[style*="color: var(--success)"],
                [data-theme=light] .tour-viewport .tour-content-panel div[style*="border-radius: 10px"] div[style*="color: var(--success)"] {
                    color: #16a34a !important;
                }
                [data-theme=light] #landing-root div[style*="rgb(9, 9, 13)"] div[style*="color: var(--text-tertiary)"],
                [data-theme=light] #landing-root div[style*="rgb(9,9,13)"] div[style*="color: var(--text-tertiary)"],
                [data-theme=light] .tour-viewport .tour-content-panel div[style*="border-radius: 10px"] div[style*="color: var(--text-tertiary)"] {
                    color: #64748b !important;
                }
                
                /* Live Sandbox (Interactive Dashboard Panel overrides) */
                [data-theme=light] .bourntec-showcase-panel {
                    background: #ffffff !important;
                    border: 1px solid #e4e4e7 !important;
                    box-shadow: 0 20px 45px rgba(0, 0, 0, 0.04) !important;
                }
                [data-theme=light] .bourntec-showcase-header {
                    background: #f8fafc !important;
                    border-bottom: 1px solid #e4e4e7 !important;
                }
                [data-theme=light] .bourntec-showcase-header span[style*="color"] {
                    color: #475569 !important;
                }
                [data-theme=light] .bourntec-showcase-tasks {
                    border-right: 1px solid #e4e4e7 !important;
                }
                [data-theme=light] .bourntec-showcase-task-card {
                    background: #f8fafc !important;
                    border: 1px solid #e4e4e7 !important;
                }
                [data-theme=light] .bourntec-showcase-task-card:hover {
                    background: #f1f5f9 !important;
                    border-color: #cbd5e1 !important;
                }
                [data-theme=light] .bourntec-showcase-task-card.active {
                    background: #f3e8ff !important;
                    border-color: #c084fc !important;
                }
                [data-theme=light] .bourntec-showcase-task-card.active span[style*="color"] {
                    color: #6b21a8 !important;
                }
                [data-theme=light] .bourntec-showcase-task-card p {
                    color: #64748b !important;
                }
                [data-theme=light] .bourntec-showcase-details {
                    background: #ffffff !important;
                }
                [data-theme=light] .bourntec-showcase-details div[style*="borderBottom"],
                [data-theme=light] .bourntec-showcase-details div[style*="border-bottom"] {
                    border-bottom-color: #e4e4e7 !important;
                }
                [data-theme=light] .bourntec-showcase-details div[style*="borderBottom"] span,
                [data-theme=light] .bourntec-showcase-details div[style*="border-bottom"] span {
                    color: #475569 !important;
                }
                
                /* Code Editor Preview & Log terminal in Sandbox details */
                [data-theme=light] .bourntec-showcase-details pre[style*="background: rgba(0, 0, 0, 0.3)"],
                [data-theme=light] .bourntec-showcase-details pre[style*="background:rgba(0,0,0,0.3)"] {
                    background: #f8fafc !important;
                    border: 1px solid #cbd5e1 !important;
                    color: #0f172a !important;
                }
                [data-theme=light] .bourntec-showcase-details pre[style*="background: #000"],
                [data-theme=light] .bourntec-showcase-details pre[style*="background:#000"] {
                    background: #f8fafc !important;
                    border: 1px solid #cbd5e1 !important;
                    color: #16a34a !important;
                }

                /* Platform Features and Metrics Section overrides */
                [data-theme=light] .bourntec-features-section {
                    background: #ffffff !important;
                }
                [data-theme=light] .bourntec-features-title {
                    color: #18181b !important;
                }
                [data-theme=light] .bourntec-feature-card {
                    background: #ffffff !important;
                    border: 1px solid #e4e4e7 !important;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.02) !important;
                }
                [data-theme=light] .bourntec-feature-card:hover {
                    background: #ffffff !important;
                    border-color: #c084fc !important;
                    box-shadow: 0 15px 35px rgba(124, 58, 237, 0.06) !important;
                    transform: translateY(-5px) !important;
                }
                [data-theme=light] .bourntec-feature-card h4 {
                    color: #18181b !important;
                }
                [data-theme=light] .bourntec-feature-card p {
                    color: #52525b !important;
                }
                [data-theme=light] .bourntec-feature-icon {
                    background: #f3e8ff !important;
                    border: 1px solid #e9d5ff !important;
                    color: #7c3aed !important;
                }
                [data-theme=light] .bourntec-metrics-section {
                    background: #fafbfc !important;
                }
                [data-theme=light] .bourntec-metric-card {
                    background: #ffffff !important;
                    border: 1px solid #e4e4e7 !important;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.02) !important;
                }
                [data-theme=light] .bourntec-metric-card:hover {
                    border-color: #cbd5e1 !important;
                }
                [data-theme=light] .bourntec-metric-value {
                    background: linear-gradient(135deg, #7c3aed 0%, #db2777 100%) !important;
                    -webkit-text-fill-color: transparent !important;
                    -webkit-background-clip: text !important;
                }
                [data-theme=light] .bourntec-metric-label {
                    color: #52525b !important;
                }

                /* Cortex card and tabs columns (third screenshot) */
                [data-theme=light] .cortex-card {
                    background: #ffffffcc !important;
                    border: 1px solid #e4e4e7 !important;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.02) !important;
                }
                [data-theme=light] .cortex-card:hover {
                    background: #ffffffdd !important;
                    border-color: #cbd5e1 !important;
                    box-shadow: 0 15px 35px rgba(0,0,0,0.05) !important;
                }
                [data-theme=light] .cortex-panel-sub-card {
                    background: #f8fafc !important;
                    border: 1px solid #e2e8f0 !important;
                }
                [data-theme=light] .cortex-panel-sub-card:hover {
                    background: #f1f5f9 !important;
                    border-color: #cbd5e1 !important;
                }
                [data-theme=light] .project-tab-btn {
                    background: #f1f5f9 !important;
                    border: 1px solid #e2e8f0 !important;
                    color: #475569 !important;
                }
                [data-theme=light] .project-tab-btn.active {
                    background: linear-gradient(135deg, #7c3aed 0%, #db2777 100%) !important;
                    color: #ffffff !important;
                }
                [data-theme=light] .checklist-item-mock {
                    background: #f8fafc !important;
                    border: 1px solid #e2e8f0 !important;
                    color: #334155 !important;
                }
                [data-theme=light] .checklist-item-mock:hover {
                    background: #f1f5f9 !important;
                    border-color: #cbd5e1 !important;
                }
                [data-theme=light] .cortex-terminal-wrapper {
                    background: #f8fafc !important;
                    border-color: #e2e8f0 !important;
                }
                [data-theme=light] .cortex-terminal-wrapper > div:first-child {
                    background: #f1f5f9 !important;
                    border-bottom-color: #e2e8f0 !important;
                }
                [data-theme=light] .cortex-terminal-wrapper div[style*="#22d3ee"],
                [data-theme=light] .cortex-terminal-wrapper div[style*="rgb(34, 211, 238)"] {
                    color: #0891b2 !important;
                }
                [data-theme=light] .cortex-terminal-wrapper div[style*="#a78bfa"],
                [data-theme=light] .cortex-terminal-wrapper div[style*="rgb(167, 139, 245)"],
                [data-theme=light] .cortex-terminal-wrapper div[style*="rgb(167, 139, 250)"] {
                    color: #7c3aed !important;
                }
                [data-theme=light] .cortex-terminal-wrapper div[style*="var(--text-secondary)"] {
                    color: #475569 !important;
                }
                [data-theme=light] .card-step-title {
                    color: #18181b !important;
                }
                [data-theme=light] .card-step-desc {
                    color: #52525b !important;
                }
                [data-theme=light] .tour-step-desc-active {
                    color: #52525b !important;
                }
            `}} />

            {/* Release Notes Modal */}
            {showReleaseNotes && (() => {
                const isLight = theme === 'light';
                const roadmapItems = [
                    {
                        version: 'v1.0 · Foundation',
                        date: 'Jan 2026',
                        title: 'Foundation: Core Orchestration',
                        status: 'done',
                        items: [
                            'BRD Intelligence Layer & Go/No-Go Governance Engine',
                            'Unified Interface Layer (SSO, Navigation)',
                            'Preview Sandbox / Vibe Coding',
                        ],
                    },
                    {
                        version: 'v1.1 · Intelligence Layer',
                        date: 'Q2 2026',
                        title: 'Intelligence Layer',
                        status: 'done',
                        items: [
                            'Agentic Workflow Engine (Subagents, Custom Skills, CLAUDE.md)',
                            'CDevSecOps Integration (GHAS, SonarQube, Azure Pipelines, Blue-Green Deployment)',
                            'Azure DevOps board integration',
                            'BYOT (Bring Your Own Tool) Framework',
                        ],
                    },
                    {
                        version: 'v2.0',
                        date: '',
                        title: 'The Bridge',
                        status: 'done',
                        items: [
                            'Agent-Native SDLC',
                            'CI/CD',
                            'Coordinated Multi-Agent Ecosystem across all SDLC functions',
                        ],
                    },
                    {
                        version: 'Future',
                        date: '',
                        title: 'Autonomous Ecosystem',
                        status: 'future',
                        items: [
                            'Citizen Development Platform',
                            'Greenfield Agentic SDLC',
                            'Brownfield Modernization Engine',
                            'Full Lifecycle Observability & Traceability',
                            'Cross-Platform Data Fabric',
                        ],
                    },
                ];
                return (
                    <div
                        onClick={() => setShowReleaseNotes(false)}
                        style={{
                            position: 'fixed', inset: 0, zIndex: 99999,
                            background: 'rgba(0,0,0,0.6)',
                            backdropFilter: 'blur(4px)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            padding: '24px',
                            fontFamily: 'system-ui, -apple-system, sans-serif',
                        }}
                    >
                        <div
                            onClick={e => e.stopPropagation()}
                            style={{
                                width: '100%', maxWidth: '560px',
                                maxHeight: '80vh',
                                overflowY: 'auto',
                                borderRadius: '16px',
                                background: isLight ? '#ffffff' : '#0f0f1a',
                                border: isLight ? '1px solid #e4e4e7' : '1px solid rgba(139,92,246,0.2)',
                                boxShadow: '0 25px 60px rgba(0,0,0,0.4)',
                                padding: '28px 28px 24px',
                            }}
                        >
                            {/* Header */}
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
                                <div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                                        <div style={{ width: '28px', height: '2px', background: 'linear-gradient(90deg,#38bdf8,#818cf8)' }} />
                                        <span style={{ fontSize: '11px', fontWeight: '700', letterSpacing: '0.12em', textTransform: 'uppercase', color: '#38bdf8' }}>Strategic Roadmap</span>
                                    </div>
                                    <h2 style={{ margin: 0, fontSize: '20px', fontWeight: '800', color: isLight ? '#18181b' : '#f1f5f9' }}>Release Notes</h2>
                                </div>
                                <button
                                    onClick={() => setShowReleaseNotes(false)}
                                    style={{
                                        background: 'none', border: 'none', cursor: 'pointer',
                                        color: isLight ? '#71717a' : '#94a3b8',
                                        fontSize: '20px', lineHeight: 1, padding: '4px',
                                        borderRadius: '6px',
                                    }}
                                >✕</button>
                            </div>

                            {/* Timeline */}
                            <div style={{ position: 'relative', paddingLeft: '32px' }}>
                                {/* Vertical line */}
                                <div style={{
                                    position: 'absolute', left: '6px', top: '8px', bottom: '8px',
                                    width: '2px',
                                    background: isLight
                                        ? 'linear-gradient(180deg,#818cf8 0%,#c084fc 60%,#e2e8f0 100%)'
                                        : 'linear-gradient(180deg,#818cf8 0%,#c084fc 60%,#334155 100%)',
                                }} />

                                {roadmapItems.map((item, idx) => {
                                    const isDone = item.status === 'done';
                                    const isFuture = item.status === 'future';
                                    return (
                                                        <div key={idx} style={{ marginBottom: idx < roadmapItems.length - 1 ? '28px' : 0, position: 'relative' }}>
                                            {/* Dot — aligned with version text */}
                                            <div style={{
                                                position: 'absolute', left: '-32px', top: '2px',
                                                width: '14px', height: '14px', borderRadius: '50%',
                                                background: isFuture
                                                    ? 'transparent'
                                                    : 'linear-gradient(135deg,#818cf8,#c084fc)',
                                                border: isFuture
                                                    ? '2px solid #a855f7'
                                                    : '2px solid transparent',
                                                boxShadow: isDone ? '0 0 0 3px rgba(129,140,248,0.15)' : 'none',
                                            }} />

                                            {/* Version / date */}
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                                                <span style={{
                                                    fontSize: '11px', fontWeight: '700',
                                                    color: isFuture
                                                        ? (isLight ? '#94a3b8' : '#64748b')
                                                        : '#818cf8',
                                                    letterSpacing: '0.04em',
                                                }}>{item.version}</span>
                                                {item.date && (
                                                    <span style={{
                                                        fontSize: '10px', fontWeight: '600',
                                                        color: isLight ? '#a1a1aa' : '#64748b',
                                                        background: isLight ? '#f4f4f5' : 'rgba(255,255,255,0.05)',
                                                        borderRadius: '4px', padding: '1px 6px',
                                                    }}>{item.date}</span>
                                                )}
                                                {isDone && (
                                                    <span style={{
                                                        fontSize: '10px', fontWeight: '700',
                                                        color: '#22c55e',
                                                        background: 'rgba(34,197,94,0.1)',
                                                        borderRadius: '4px', padding: '1px 6px',
                                                        letterSpacing: '0.04em',
                                                    }}>✓ Done</span>
                                                )}
                                                {isFuture && (
                                                    <span style={{
                                                        fontSize: '10px', fontWeight: '700',
                                                        color: '#f59e0b',
                                                        background: 'rgba(245,158,11,0.1)',
                                                        borderRadius: '4px', padding: '1px 6px',
                                                        letterSpacing: '0.04em',
                                                    }}>⏳ Planned</span>
                                                )}
                                            </div>

                                            {/* Title */}
                                            <div style={{
                                                fontSize: '15px', fontWeight: '700',
                                                color: isFuture
                                                    ? (isLight ? '#71717a' : '#64748b')
                                                    : (isLight ? '#18181b' : '#f1f5f9'),
                                                marginBottom: '8px',
                                            }}>{item.title}</div>

                                            {/* Items */}
                                            <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '5px' }}>
                                                {item.items.map((feat, fi) => (
                                                    <li key={fi} style={{
                                                        fontSize: '13px',
                                                        color: isFuture
                                                            ? (isLight ? '#a1a1aa' : '#64748b')
                                                            : (isLight ? '#52525b' : '#94a3b8'),
                                                        display: 'flex', alignItems: 'flex-start', gap: '6px',
                                                    }}>
                                                        <span style={{ color: isFuture ? (isLight ? '#cbd5e1' : '#475569') : '#818cf8', marginTop: '2px', flexShrink: 0 }}>›</span>
                                                        {feat}
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>
                );
            })()}
        </>
    );
}
