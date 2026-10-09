import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { Platform } from 'react-native';

/**
 * Width the sheet is downscaled to before upload.
 *
 * The OMR engine normalises every sheet to 1600px wide before it fits the
 * bubble lattice (backend_mcq_final/omr_mcq/reader.py: WORKING_WIDTH), so
 * anything larger is decoded and thrown away server-side. Matching that
 * number keeps every pixel the reader actually uses and discards the rest.
 */
export const UPLOAD_WIDTH = 1600;

/**
 * Shrink a camera photo to what the reader needs.
 *
 * A phone camera at quality 0.85 produces a 4000x3000, 5-12 MB JPEG. Pushing
 * that over WiFi is slow and fails often -- and when the multipart POST dies
 * mid-transfer the app could only report "cannot reach the server", which
 * looks like the backend is down when it is actually running fine. Resizing
 * first turns a multi-megabyte upload into a few hundred KB.
 *
 * Returns the original URI unchanged if manipulation fails: a larger upload
 * that might work beats refusing to scan at all.
 */
export type PreparedSheet = {
    uri: string;
    /** Name and type always describe the bytes actually being sent. */
    name: string;
    type: string;
};

export async function prepareSheetForUpload(
    uri: string,
    originalName = 'sheet.jpg',
): Promise<PreparedSheet> {
    // Web already hands us a blob-backed URI from the file picker, and the
    // native manipulator is not the right tool there.
    if (Platform.OS === 'web') {
        const isPng = originalName.toLowerCase().endsWith('.png');
        return {
            uri,
            name: originalName,
            type: isPng ? 'image/png' : 'image/jpeg',
        };
    }

    try {
        const ctx = ImageManipulator.manipulate(uri).resize({ width: UPLOAD_WIDTH });
        const image = await ctx.renderAsync();
        // 0.85 keeps bubble edges crisp; the reader thresholds ink, so mild
        // JPEG ringing is harmless but heavy compression is not.
        const saved = await image.saveAsync({
            format: SaveFormat.JPEG,
            compress: 0.85,
        });
        // `saved` is a native-backed result: read the uri off it explicitly
        // and check it, rather than trusting the object to survive the spread
        // that FormData.getParts() performs. A part that reaches the native
        // layer without a usable `uri` fails with "Unsupported FormData part".
        const out = typeof saved?.uri === 'string' ? saved.uri : '';
        if (out) {
            // The output is JPEG whatever the source was, so the name and type
            // say so. A picker-supplied ".png" name on JPEG bytes is a lie
            // that some multipart encoders and servers reject.
            return { uri: normaliseUri(out), name: 'sheet.jpg', type: 'image/jpeg' };
        }
    } catch {
        // fall through to the original image
    }

    const isPng = originalName.toLowerCase().endsWith('.png');
    return {
        uri: normaliseUri(uri),
        name: originalName,
        type: isPng ? 'image/png' : 'image/jpeg',
    };
}

/**
 * Give the URI a scheme React Native's uploader accepts.
 *
 * A bare filesystem path ("/data/user/0/.../sheet.jpg") is rejected by the
 * native multipart encoder, which only understands a scheme it can open.
 */
function normaliseUri(uri: string): string {
    return /^[a-z][a-z0-9+.-]*:/i.test(uri) ? uri : `file://${uri}`;
}
