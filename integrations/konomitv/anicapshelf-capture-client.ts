export type AniCapShelfTag = string;

export type KonomiTVRecordedProgram = {
  id?: number | string;
  title?: string;
  series_title?: string | null;
  episode_number?: number | null;
  subtitle?: string | null;
  start_time?: string | number | null;
  end_time?: string | number | null;
  recorded_video?: {
    id?: number | string;
    file_path?: string | null;
    duration?: number | null;
  } | null;
};

export type AniCapShelfCaptureInput = {
  endpoint?: string;
  image: Blob;
  filename: string;
  recordedProgram?: KonomiTVRecordedProgram | null;
  playbackPositionSeconds?: number | null;
  capturedAt?: Date;
  tags?: AniCapShelfTag[];
  note?: string;
  konomitvUrl?: string;
};

export type AniCapShelfCaptureResponse = {
  capture_id: number;
  annotation_id: number;
  image_path: string;
};

const DEFAULT_ENDPOINT = "http://127.0.0.1:8765/api/captures/annotated";

export async function uploadAnnotatedCapture(
  input: AniCapShelfCaptureInput,
): Promise<AniCapShelfCaptureResponse> {
  const endpoint = input.endpoint ?? DEFAULT_ENDPOINT;
  const metadata = buildKonomiTVMetadata(input);
  const formData = new FormData();
  formData.append("image", input.image, input.filename);
  formData.append("metadata", JSON.stringify(metadata));
  if (input.tags && input.tags.length > 0) {
    formData.append("tags", JSON.stringify(input.tags));
  }
  if (input.note) {
    formData.append("note", input.note);
  }

  const response = await fetch(endpoint, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`AniCapShelf upload failed: ${response.status} ${message}`);
  }
  return (await response.json()) as AniCapShelfCaptureResponse;
}

export function buildKonomiTVMetadata(input: AniCapShelfCaptureInput): Record<string, unknown> {
  const recordedProgram = input.recordedProgram;
  const recordedVideo = recordedProgram?.recorded_video;
  return {
    source_app: "KonomiTV",
    captured_at: (input.capturedAt ?? new Date()).toISOString(),
    recorded_program_id: recordedProgram?.id ?? null,
    recorded_video_id: recordedVideo?.id ?? null,
    recording_file_path: recordedVideo?.file_path ?? null,
    playback_position_seconds: input.playbackPositionSeconds ?? null,
    title: recordedProgram?.title ?? null,
    series_title: recordedProgram?.series_title ?? null,
    episode_number: recordedProgram?.episode_number ?? null,
    subtitle: recordedProgram?.subtitle ?? null,
    start_time: normalizeKonomiTVTime(recordedProgram?.start_time),
    end_time: normalizeKonomiTVTime(recordedProgram?.end_time),
    recorded_video_duration_seconds: recordedVideo?.duration ?? null,
    konomitv_url: input.konomitvUrl ?? globalThis.location?.href ?? null,
  };
}

export function normalizeKonomiTVTime(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value === "number") {
    return new Date(value * 1000).toISOString();
  }
  return value;
}

