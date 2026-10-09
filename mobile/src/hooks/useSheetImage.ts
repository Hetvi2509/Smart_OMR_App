import { useEffect, useState } from 'react';
import { Platform } from 'react-native';

import { sheetImageSource } from '../api/endpoints';

export type SheetVariant = 'original' | 'annotated';

/**
 * A displayable source for a submission's sheet image.
 *
 * `variant` picks between the photo as uploaded and the engine's review
 * overlay, which rings every bubble the algorithm detected.
 *
 * The route is authenticated, and the image is always fetched explicitly
 * with the bearer header rather than handed to <Image source={{uri,
 * headers}}> to let React Native's native image loader attach it. That used
 * to work; on this SDK it silently did not -- the image never rendered and
 * no error surfaced, because the failure is inside native code the JS layer
 * never sees. Fetching here, with the same `fetch` this app's uploads
 * already go through successfully, sidesteps that native path entirely.
 *
 * Native gets a data: URI (via FileReader, built into React Native) and web
 * gets an object URL -- both are things <Image>/<img> can always display
 * with no further native involvement.
 */
export function useSheetImage(submissionId: number, variant: SheetVariant = 'original') {
    const [uri, setUri] = useState<string | null>(null);
    const [failed, setFailed] = useState(false);

    useEffect(() => {
        const { uri: url, headers } = sheetImageSource(submissionId, variant);
        setFailed(false);
        setUri(null);

        let objectUrl: string | null = null;
        let cancelled = false;

        (async () => {
            try {
                const res = await fetch(url, { headers });
                if (!res.ok) throw new Error(String(res.status));
                const blob = await res.blob();
                if (cancelled) return;

                if (Platform.OS === 'web') {
                    objectUrl = URL.createObjectURL(blob);
                    setUri(objectUrl);
                    return;
                }

                // FileReader.readAsDataURL ships with React Native; using it
                // avoids adding a dependency for what is otherwise a few
                // lines of glue around a callback-based API.
                const dataUri = await new Promise<string>((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = () => resolve(reader.result as string);
                    reader.onerror = () => reject(reader.error ?? new Error('read failed'));
                    reader.readAsDataURL(blob);
                });
                if (!cancelled) setUri(dataUri);
            } catch {
                if (!cancelled) setFailed(true);
            }
        })();

        return () => {
            cancelled = true;
            if (objectUrl) URL.revokeObjectURL(objectUrl);
        };
    }, [submissionId, variant]);

    return {
        source: uri ? { uri } : null,
        failed,
    };
}
