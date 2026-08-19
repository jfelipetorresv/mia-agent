// Mia · CP-Z1b — hook del dictado por voz (botón de micrófono).
//
// Ciclo: inactivo → (clic) grabando → (clic) transcribiendo → texto insertado.
// Captura con Web Audio (AudioContext + ScriptProcessorNode) acumulando Float32:
// MediaRecorder NO sirve (webm/opus; el backend solo decodifica WAV PCM).
// ScriptProcessorNode está deprecado pero es universal y simple — decisión
// consciente para v1; migrar a AudioWorklet si algún navegador lo retira.
// El permiso de micrófono se pide en el PRIMER clic, nunca al cargar la página.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiGet, apiUploadBlob } from "./api";
import { encodeWavPcm16, resampleTo16kMono } from "./wav";

export type DictationState = "inactivo" | "grabando" | "transcribiendo";

// El backend rechaza clips de más de 5 minutos: se corta solo antes de llegar.
const MAX_SECONDS = 300;

type SpeechStatus = { estado: string; listo: boolean; mensaje: string };
type TranscribeResponse = {
  text: string;
  cleaned_text: string | null;
  message: string | null;
};

export function useDictation(
  onText: (text: string) => void,
  onNotice?: (notice: string) => void,
) {
  const [state, setState] = useState<DictationState>("inactivo");
  const [error, setError] = useState<string | null>(null);
  // null = aún no se consultó; el botón se muestra igual y el clic informa.
  const [available, setAvailable] = useState<boolean | null>(null);
  const [unavailableMsg, setUnavailableMsg] = useState<string>("");

  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const samplesRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const busyRef = useRef(false);
  // Guard de arranque (hallazgo capa 2 #2): el diálogo de permiso del navegador
  // deja una ventana en la que un segundo clic arrancaría una SEGUNDA captura
  // (mic huérfano capturando para siempre). Con esto, ese clic no hace nada.
  const startingRef = useRef(false);
  const aliveRef = useRef(true);

  useEffect(() => {
    let alive = true;
    apiGet<SpeechStatus>("/api/speech/status")
      .then((s) => {
        if (!alive) return;
        setAvailable(Boolean(s.listo));
        if (!s.listo) setUnavailableMsg(s.mensaje);
      })
      .catch(() => {
        // Sin estado no se bloquea el botón: el propio dictado explicará.
        if (alive) setAvailable(null);
      });
    return () => {
      alive = false;
      aliveRef.current = false;
      teardownCapture();
    };
  }, []);

  function teardownCapture() {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    processorRef.current?.disconnect();
    processorRef.current = null;
    sourceRef.current?.disconnect();
    sourceRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    void ctxRef.current?.close().catch(() => {});
    ctxRef.current = null;
  }

  const stopAndTranscribe = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    const chunks = chunksRef.current;
    const rate = ctxRef.current?.sampleRate ?? 48000;
    teardownCapture();
    setState("transcribiendo");
    try {
      const samples = await resampleTo16kMono(chunks, rate);
      chunksRef.current = [];
      samplesRef.current = 0;
      const wav = encodeWavPcm16(samples);
      const r = await apiUploadBlob<TranscribeResponse>(
        "/api/speech/transcribe",
        "audio",
        wav,
        "dictado.wav",
        { pulir: "true" },
      );
      if (r.message) {
        onNotice?.(r.message);
      }
      const text = (r.cleaned_text ?? r.text ?? "").trim();
      if (text) onText(text);
    } catch (e) {
      if (e instanceof ApiError) {
        // El backend redacta el detail en llano (400/413/429/503) — tal cual.
        setError(e.message);
      } else {
        setError("No se pudo enviar el dictado. Revisa tu conexión e intenta de nuevo.");
      }
    } finally {
      busyRef.current = false;
      setState("inactivo");
    }
  }, [onText, onNotice]);

  const startRecording = useCallback(async () => {
    // Un arranque a la vez: si ya hay una captura viva o el permiso está en
    // pantalla, el clic extra se ignora (nunca dos micrófonos abiertos).
    if (startingRef.current || streamRef.current || busyRef.current) return;
    startingRef.current = true;
    setError(null);
    if (available === false) {
      setError(
        unavailableMsg ||
          "El dictado por voz no está instalado. Instálalo desde el Panel de control.",
      );
      startingRef.current = false;
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1 },
      });
    } catch {
      setError(
        "Mia no tiene permiso para usar tu micrófono. Habilítalo en el navegador e intenta de nuevo.",
      );
      startingRef.current = false;
      return;
    }
    if (!aliveRef.current) {
      // El abogado navegó a otra pantalla mientras el permiso estaba en
      // pantalla: no dejar el micrófono capturando huérfano.
      stream.getTracks().forEach((t) => t.stop());
      startingRef.current = false;
      return;
    }
    try {
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const processor = ctx.createScriptProcessor(4096, 1, 1);
      chunksRef.current = [];
      samplesRef.current = 0;
      processor.onaudioprocess = (ev) => {
        const data = ev.inputBuffer.getChannelData(0);
        chunksRef.current.push(new Float32Array(data));
        samplesRef.current += data.length;
      };
      source.connect(processor);
      processor.connect(ctx.destination);
      streamRef.current = stream;
      ctxRef.current = ctx;
      sourceRef.current = source;
      processorRef.current = processor;
      setState("grabando");
      // Autocorte ANTES del tope del servidor (5 min): el dictado llega completo.
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        void stopAndTranscribe();
      }, MAX_SECONDS * 1000);
    } catch {
      // Si el armado de la captura falla, el micrófono no queda abierto ni el
      // botón muerto (nota capa 2: sin esto, startingRef quedaba atascado).
      stream.getTracks().forEach((t) => t.stop());
      setError("No se pudo iniciar la grabación. Vuelve a intentarlo.");
    } finally {
      startingRef.current = false;
    }
  }, [available, unavailableMsg, stopAndTranscribe]);

  const toggle = useCallback(() => {
    if (state === "grabando") {
      void stopAndTranscribe();
    } else if (state === "inactivo") {
      void startRecording();
    }
    // "transcribiendo": se ignora el clic — la respuesta está en camino.
  }, [state, startRecording, stopAndTranscribe]);

  return { state, error, available, toggle };
}
