// Mia · CP-Z1b — empaquetado de audio para el dictado local.
//
// El backend (POST /api/speech/transcribe) solo decodifica WAV PCM: por eso el
// micrófono NO usa MediaRecorder (produce webm/opus comprimido) sino Web Audio,
// y este módulo re-muestrea a 16 kHz mono y arma el WAV PCM16 en el navegador
// (~40 líneas, sin librerías). El AudioContext del navegador abre a 44.1/48 kHz
// según el equipo — el re-muestreo es obligatorio, no opcional.

/** Concatena los trozos Float32 capturados y los re-muestrea a 16 kHz mono. */
export async function resampleTo16kMono(
  chunks: Float32Array[],
  sourceRate: number,
): Promise<Float32Array> {
  let total = 0;
  for (const c of chunks) total += c.length;
  const joined = new Float32Array(total);
  let offset = 0;
  for (const c of chunks) {
    joined.set(c, offset);
    offset += c.length;
  }
  if (total === 0) return joined;
  if (sourceRate === 16000) return joined;
  const targetLength = Math.max(1, Math.round((total * 16000) / sourceRate));
  const ctx = new OfflineAudioContext(1, targetLength, 16000);
  const buffer = ctx.createBuffer(1, total, sourceRate);
  buffer.copyToChannel(joined, 0);
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.connect(ctx.destination);
  source.start();
  const rendered = await ctx.startRendering();
  return rendered.getChannelData(0).slice();
}

/** Float32 [-1,1] a 16 kHz → Blob WAV PCM16 mono listo para subir. */
export function encodeWavPcm16(samples: Float32Array, sampleRate = 16000): Blob {
  const dataBytes = samples.length * 2;
  const buf = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buf);
  const writeStr = (pos: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(pos + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true); // tamaño del bloque fmt
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // bytes por segundo
  view.setUint16(32, 2, true); // bytes por muestra
  view.setUint16(34, 16, true); // bits por muestra
  writeStr(36, "data");
  view.setUint32(40, dataBytes, true);
  let pos = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(pos, s < 0 ? s * 32768 : s * 32767, true);
    pos += 2;
  }
  return new Blob([buf], { type: "audio/wav" });
}
