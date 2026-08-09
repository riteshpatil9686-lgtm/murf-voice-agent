'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  useAgent,
  useSessionContext,
  useSessionMessages,
  useTrackVolume,
  useVoiceAssistant,
} from '@livekit/components-react';
import { ConnectionState } from 'livekit-client';
import { Github, Globe, Linkedin, Loader2, Mic, Square, Volume2 } from 'lucide-react';
import { useSession } from 'next-auth/react';
import { SignOutButton } from '@/components/app/auth-gate';
import { cn } from '@/lib/shadcn/utils';

export function DeutschMateView() {
  const { data: authSession } = useSession();
  const learnerFirstName = authSession?.user?.name?.split(' ')[0] ?? 'Learner';

  const session = useSessionContext();
  const { state: agentState } = useAgent();
  const { messages } = useSessionMessages(session);
  const { audioTrack } = useVoiceAssistant();
  const volume = useTrackVolume(audioTrack);

  // Track if user has connected at least once during this page session
  const [hasStarted, setHasStarted] = useState(false);

  useEffect(() => {
    if (session.isConnected) {
      setHasStarted(true);
    }
  }, [session.isConnected]);

  // Video playback speed setup
  const videoRef = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.playbackRate = 0.5;
    }
  }, []);

  // Determine actual agent state from LiveKit
  const isConnecting =
    session.connectionState === ConnectionState.Connecting ||
    agentState === 'connecting' ||
    agentState === 'initializing';
  const isConnected = session.isConnected;
  const isListening = isConnected && agentState === 'listening';
  const isThinking = isConnected && agentState === 'thinking';
  const isSpeaking = isConnected && agentState === 'speaking';
  const isEnded = hasStarted && !isConnected && !isConnecting;

  // Extract latest user and agent transcripts
  const lastUserMsg = messages.filter((m) => m.from?.isLocal).at(-1)?.message;
  const lastAgentMsg = messages.filter((m) => !m.from?.isLocal).at(-1)?.message;

  // Handle main microphone button click
  const handleMainButtonClick = () => {
    if (isConnecting) return;
    if (isConnected) {
      session.end();
    } else {
      session.start();
    }
  };

  return (
    <div className="bg-black text-white relative flex h-screen min-h-screen w-full flex-col justify-between overflow-hidden selection:bg-white selection:text-black">
      {/* FULLSCREEN BACKGROUND VIDEO */}
      <video
        ref={videoRef}
        id="hero-video"
        className="absolute inset-0 z-0 h-full w-full object-cover object-bottom"
        src="https://designerstephen.github.io/public-assets/videos/observe-hero.mp4"
        muted
        autoPlay
        loop
        playsInline
        preload="auto"
      />

      {/* NAVBAR */}
      <nav className="relative z-20 w-full shrink-0 px-6 py-5">
        <div className="liquid-glass mx-auto flex max-w-5xl items-center justify-between rounded-full py-1.5 pr-2 pl-6">
          {/* Logo & Name */}
          <div className="flex items-center gap-3">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
              className="text-white size-6 shrink-0"
            >
              <path
                d="M4.21 16.5 A9 9 0 0 1 16.5 4.21"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
              <path
                d="M16.5 4.21 A9 9 0 0 1 19.79 16.5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeDasharray="2.4 2.3"
              />
              <path
                d="M19.79 16.5 A9 9 0 0 1 4.21 16.5"
                stroke="currentColor"
                strokeWidth="2.6"
                strokeLinecap="round"
                strokeDasharray="0.01 4.7"
              />
              <circle cx="12" cy="12" r="2.5" fill="currentColor" />
            </svg>
            <span className="font-semibold text-lg tracking-tight select-none">DeutschMate</span>

            {/* Desktop Navigation Links */}
            <div className="hidden gap-8 md:flex md:ml-8">
              <a
                href="#about"
                className="text-white/80 hover:text-white text-sm font-medium transition-colors"
              >
                About
              </a>
              <a
                href="#how-it-works"
                className="text-white/80 hover:text-white text-sm font-medium transition-colors"
              >
                How it works
              </a>
              <a
                href="#practice"
                className="text-white/80 hover:text-white text-sm font-medium transition-colors"
              >
                Practice
              </a>
            </div>
          </div>

          {/* Right Status Group */}
          <div className="flex items-center gap-3">
            <span className="text-white/80 text-xs font-medium md:text-sm px-2">EN / DE</span>
            <div className="liquid-glass text-white/90 flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium">
              <span className="bg-white size-2 rounded-full animate-pulse" />
              <span>AI Tutor</span>
            </div>
            <SignOutButton />
          </div>
        </div>
      </nav>

      {/* HERO & VOICE INTERACTION CORE */}
      <div className="-translate-y-[4%] md:-translate-y-[6%] relative z-10 mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center px-6 text-center">
        {/* Main Headline */}
        <h1
          className="font-serif-instrument text-4xl sm:text-6xl md:text-7xl lg:text-8xl mb-3 tracking-tight whitespace-nowrap select-none"
          style={{ textShadow: '0 0 80px rgba(0, 0, 0, 0.7), 0 4px 30px rgba(0, 0, 0, 0.6), 0 1px 4px rgba(0, 0, 0, 0.8)' }}
        >
          Language is learned in <em className="font-normal italic">conversation.</em>
        </h1>

        {/* Subline & Secondary line */}
        <p
          className="text-white/85 mb-1 max-w-2xl text-sm leading-relaxed select-none md:text-base font-normal"
          style={{ textShadow: '0 2px 16px rgba(0, 0, 0, 0.7)' }}
        >
          Your AI German tutor for natural, everyday conversations.
        </p>
        <p
          className="text-white/70 mb-4 max-w-xl text-xs select-none md:text-sm font-normal"
          style={{ textShadow: '0 2px 12px rgba(0, 0, 0, 0.6)' }}
        >
          Practice vocabulary, pronunciation, grammar, and real conversations.
        </p>

        {/* Personalization Greeting */}
        <div className="mb-4 text-center">
          <p
            className="text-white/95 text-base font-semibold md:text-lg tracking-tight"
            style={{ textShadow: '0 2px 10px rgba(0, 0, 0, 0.6)' }}
          >
            Hallo, {learnerFirstName}.
          </p>
          <p
            className="text-white/75 text-xs md:text-sm font-normal mt-0.5"
            style={{ textShadow: '0 2px 10px rgba(0, 0, 0, 0.6)' }}
          >
            Ready to practice some German?
          </p>
        </div>

        {/* VOICE AGENT CORE BUTTON & VISUALIZER */}
        <div className="relative my-2 flex flex-col items-center">
          {/* Subtle Audio Visualizer Ring / Breathing bars */}
          <div className="relative flex items-center justify-center">
            {/* Animated breathing / ripple rings */}
            {isListening && (
              <div className="pointer-events-none absolute inset-0 rounded-full border border-white/40 scale-125 duration-1000 animate-ping" />
            )}
            {isSpeaking && (
              <div
                className="pointer-events-none absolute -inset-3 rounded-full border border-white/30 animate-pulse"
                style={{ transform: `scale(${1 + Math.min((volume || 0.1) * 2, 0.3)})` }}
              />
            )}

            {/* Visualizer Bars around Circle */}
            <div className="pointer-events-none absolute inset-0 -m-4 flex items-center justify-center">
              <div className="flex h-20 w-36 items-center justify-center gap-1.5">
                {[...Array(10)].map((_, i) => {
                  const h = isSpeaking
                    ? Math.max(8, Math.min(60, ((volume || 0.1) * 100 * ((i % 5) + 1)) / 2))
                    : isListening
                      ? 12 + Math.sin(Date.now() / 200 + i) * 6
                      : 4;
                  return (
                    <span
                      key={i}
                      className="bg-white/60 w-1 rounded-full transition-all duration-150"
                      style={{ height: `${h}px`, opacity: isConnected ? 0.8 : 0.2 }}
                    />
                  );
                })}
              </div>
            </div>

            {/* Central Large Liquid Glass Microphone Circle */}
            <button
              onClick={handleMainButtonClick}
              disabled={isConnecting}
              aria-label={
                isConnecting
                  ? 'Connecting to DeutschMate'
                  : isConnected
                    ? 'End conversation with DeutschMate'
                    : 'Start talking to DeutschMate'
              }
              className={cn(
                'liquid-glass-circle relative z-20 flex size-28 cursor-pointer items-center justify-center rounded-full text-white transition-all duration-300 select-none group md:size-32 focus:outline-none focus:ring-2 focus:ring-white/50',
                isConnecting && 'opacity-70 cursor-not-allowed',
                isListening && 'scale-105 shadow-[0_0_30px_rgba(255,255,255,0.2)]',
                isSpeaking && 'scale-105 shadow-[0_0_40px_rgba(255,255,255,0.3)]',
                !isConnected && !isConnecting && 'hover:scale-105 active:scale-95'
              )}
            >
              {isConnecting ? (
                <Loader2 className="text-white/80 size-10 animate-spin" />
              ) : isSpeaking ? (
                <Volume2 className="text-white size-10 animate-pulse" />
              ) : isConnected ? (
                <Square className="text-white fill-white size-8" />
              ) : (
                <Mic className="text-white group-hover:scale-110 size-10 transition-transform" />
              )}
            </button>
          </div>

          {/* State Label under Circle */}
          <div className="mt-3 text-center">
            <span
              className="text-white block font-medium text-base tracking-tight md:text-lg"
              style={{ textShadow: '0 2px 10px rgba(0, 0, 0, 0.7)' }}
            >
              {isConnecting
                ? 'Connecting...'
                : isListening
                  ? 'Listening...'
                  : isThinking
                    ? 'Thinking...'
                    : isSpeaking
                      ? 'DeutschMate is speaking...'
                      : isEnded
                        ? 'Start again'
                        : 'Start talking'}
            </span>
            {isConnecting && (
              <span className="text-white/70 mt-0.5 block text-xs">Please wait</span>
            )}
          </div>
        </div>

        {/* Code-Mixed Language Capability Indicator */}
        <div className="mt-2 mb-3">
          <div className="liquid-glass bg-black/40 text-white/85 inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-medium shadow-lg backdrop-blur-md">
            <span>Deutsch</span>
            <span className="text-white/40">•</span>
            <span>English</span>
            <span className="text-white/40">•</span>
            <span>हिन्दी</span>
          </div>
        </div>

        {/* Live Transcript Display - Subtle Liquid Glass Pill/Card */}
        <div className="flex min-h-[72px] w-full max-w-lg flex-col items-center justify-center px-2 py-1">
          <div className="liquid-glass bg-black/40 backdrop-blur-md rounded-2xl px-6 py-3.5 border border-white/10 shadow-xl w-full text-center space-y-2">
            {isConnected || isEnded ? (
              <div className="w-full space-y-2">
                {lastUserMsg && (
                  <div>
                    <span className="text-white/90 font-medium block text-[11px] tracking-wider uppercase">You</span>
                    <p className="text-white/75 text-xs md:text-sm leading-relaxed">
                      &ldquo;{lastUserMsg}&rdquo;
                    </p>
                  </div>
                )}
                {lastAgentMsg && (
                  <div>
                    <span className="text-white/90 font-semibold block text-[11px] tracking-wider uppercase">DeutschMate</span>
                    <p className="text-white/75 text-xs md:text-sm leading-relaxed">
                      &ldquo;{lastAgentMsg}&rdquo;
                    </p>
                  </div>
                )}
                {!lastUserMsg && !lastAgentMsg && (
                  <div>
                    <span className="text-white/90 font-semibold block text-[11px] tracking-wider uppercase mb-0.5">DeutschMate</span>
                    <p className="text-white/75 text-xs md:text-sm leading-relaxed">
                      &ldquo;Hallo! Ich bin DeutschMate. Bereit, Deutsch zu sprechen?&rdquo;
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div>
                <span className="text-white/90 font-semibold block text-[11px] tracking-wider uppercase mb-0.5">DeutschMate</span>
                <p className="text-white/75 text-xs md:text-sm leading-relaxed">
                  &ldquo;Hallo! Ich bin DeutschMate. Bereit, Deutsch zu sprechen?&rdquo;
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Learning Mode Pill */}
        <div className="mt-3">
          <div className="liquid-glass bg-black/40 text-white/75 rounded-full px-4 py-1 text-xs font-medium backdrop-blur-md shadow-md">
            Practice Mode · Beginner
          </div>
        </div>
      </div>

      {/* FOOTER / BOTTOM AREA */}
      <footer className="relative z-10 flex shrink-0 flex-col items-center gap-3 pt-2 pb-5">
        {/* 3 Circular Social Buttons */}
        <div className="flex justify-center gap-4">
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="GitHub"
            className="liquid-glass-circle text-white/80 hover:text-white hover:bg-white/5 flex size-11 items-center justify-center rounded-full transition-all active:scale-95"
          >
            <Github className="size-5" />
          </a>
          <a
            href="https://linkedin.com"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="LinkedIn"
            className="liquid-glass-circle text-white/80 hover:text-white hover:bg-white/5 flex size-11 items-center justify-center rounded-full transition-all active:scale-95"
          >
            <Linkedin className="size-5" />
          </a>
          <a
            href="https://voiceforbharat.org"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Project Website"
            className="liquid-glass-circle text-white/80 hover:text-white hover:bg-white/5 flex size-11 items-center justify-center rounded-full transition-all active:scale-95"
          >
            <Globe className="size-5" />
          </a>
        </div>

        {/* Branding */}
        <p
          className="text-white/65 text-xs tracking-wide"
          style={{ textShadow: '0 1px 8px rgba(0, 0, 0, 0.6)' }}
        >
          Built for VoiceForBharat · Powered by Murf Falcon
        </p>
      </footer>
    </div>
  );
}
