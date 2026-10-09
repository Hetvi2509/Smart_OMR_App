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
 * The route is authenticated. React Native's <Image> can send the bearer
 * token as a request header, but a browser's <img> cannot -- so on web the
 * image is fetched with the header and turned into an object URL instead.
 * Putting the token in the query string would be simpler and is exactly what
 * this avoids: it would leak into browser history, logs and proxy caches.
 */
export function useSheetImage(submissionId: number, variant: SheetVariant = 'original') {
    const [uri, setUri] = useState<string | null>(null);
    const [failed, setFailed] = useState(false);

    useEffect(() => {
        const native = sheetImageSource(submissionId, variant);
        setFailed(false);

        if (Platform.OS !== 'web') {
            setUri(native.uri);
            return;
        }

        let objectUrl: string | null = null;
        let cancelled = false;
        setUri(null);

        (async () => {
            try {
                const res = await fetch(native.uri, { headers: native.headers });
                if (!res.ok) throw new Error(String(res.status));
                const blob = await res.blob();
                if (cancelled) return;
                objectUrl = URL.createObjectURL(blob);
                setUri(objectUrl);
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
        // Native keeps the headers; web has already baked auth into the blob.
        source: uri
            ? (Platform.OS === 'web'
                ? { uri }
                : { uri, headers: sheetImageSource(submissionId, variant).headers })
            : null,
        failed,
    };
}
