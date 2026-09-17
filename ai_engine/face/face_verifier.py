"""
FaceVerifier — High-Accuracy Modular Identity-Verification Component for Project Garuda.

Features:
  - Deep Feature Extraction via InceptionResnetV1 (FaceNet VGGFace2 512-D embeddings).
  - High-Speed Face Localization via OpenCV YuNet (cv2.FaceDetectorYN) & Haar Cascade.
  - Zero External Dlib/CMake Dependency: Runs natively with PyTorch & OpenCV.
  - Conservative Thresholding: Unknowns flagged safely as UNKNOWN / VERIFICATION_REQUIRED.
  - Cosine Similarity Matching with Fast Vectorized Matrix Dot-Products.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Tuple
import cv2
import numpy as np

logger = logging.getLogger("garude.face_verifier")


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNKNOWN = "UNKNOWN"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    NO_FACE_DETECTED = "NO_FACE_DETECTED"
    DISGUISE_DETECTED = "DISGUISE_DETECTED"


@dataclass
class EnrolledIdentity:
    identity_id: str
    name: str
    role: str
    embedding: np.ndarray  # 512-d float32 L2-normalized vector
    rank_stars: int = 1
    rank_title: str = "Officer"


@dataclass
class VerificationResult:
    status: VerificationStatus
    identity_id: Optional[str]
    name: Optional[str]
    confidence: float  # 0.0 - 1.0, higher = more confident
    role: Optional[str] = None
    rank_stars: int = 1
    rank_title: str = "Officer"
    is_disguised: bool = False
    disguise_type: Optional[str] = None


class FaceVerifier:
    """
    Project Garuda Neural Face Verifier.
    Uses FaceNet InceptionResnetV1 (512-D embeddings) and OpenCV YuNet/Haar.
    """

    MATCH_THRESHOLD = 0.74           # Cosine similarity threshold for verified identity (calibrated for real-world ambient CCTV/webcam)
    LOW_CONFIDENCE_THRESHOLD = 0.65  # Threshold for attention / low-confidence flag
    INPUT_SIZE = (160, 160)

    def __init__(self, model_dir: Optional[str] = None):
        self._enrolled: List[EnrolledIdentity] = []
        self._enrolled_matrix: Optional[np.ndarray] = None  # (N, 512) for vectorized search
        self._device = "cpu"
        self._resnet = None
        self._yunet_detector = None
        self._haar_cascade = None
        self._backend_available = False

        self._init_models(model_dir)

    def _init_models(self, model_dir: Optional[str] = None):
        """Initialize neural embedding model and face detector."""
        # 1. Initialize PyTorch InceptionResnetV1 (FaceNet)
        try:
            import torch
            from facenet_pytorch import InceptionResnetV1

            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            self._resnet = InceptionResnetV1(pretrained="vggface2").eval().to(self._device)
            self._backend_available = True
            logger.info("FaceVerifier: InceptionResnetV1 (vggface2) loaded successfully on %s", self._device)
        except Exception as e:
            logger.warning("FaceVerifier: Could not initialize InceptionResnetV1: %s. Using histogram fallback.", e)
            self._backend_available = False

        # 2. Initialize YuNet Face Detector
        base_dir = model_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
        yunet_path = os.path.join(base_dir, "face_detection_yunet_2023mar.onnx")

        if os.path.exists(yunet_path) and hasattr(cv2, "FaceDetectorYN"):
            try:
                self._yunet_detector = cv2.FaceDetectorYN.create(
                    yunet_path, "", (320, 320), score_threshold=0.45, nms_threshold=0.3
                )
                logger.info("FaceVerifier: YuNet FaceDetectorYN initialized from %s", yunet_path)
            except Exception as e:
                logger.warning("FaceVerifier: YuNet init failed: %s", e)

        # 3. Initialize OpenCV Haar Cascade fallback
        try:
            haar_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            if os.path.exists(haar_path):
                self._haar_cascade = cv2.CascadeClassifier(haar_path)
                logger.info("FaceVerifier: Haar Cascade fallback initialized.")
        except Exception as e:
            logger.warning("FaceVerifier: Haar cascade init failed: %s", e)

    def _rebuild_enrolled_matrix(self):
        """Rebuilds the (N, 512) matrix of normalized embeddings for fast matrix multiplication."""
        if not self._enrolled:
            self._enrolled_matrix = None
            return
        vectors = []
        for e in self._enrolled:
            v = np.asarray(e.embedding, dtype=np.float32)
            norm = np.linalg.norm(v)
            if norm > 1e-6:
                v = v / norm
            vectors.append(v)
        self._enrolled_matrix = np.vstack(vectors)

    def detect_face(self, image: np.ndarray) -> Optional[np.ndarray]:
        """
        Locates and crops the most prominent face from an image.
        Returns a normalized 160x160 BGR face image.
        """
        if image is None or image.size == 0:
            return None

        h, w = image.shape[:2]
        if h < 20 or w < 20:
            return None

        # Method A: YuNet
        if self._yunet_detector is not None:
            try:
                self._yunet_detector.setInputSize((w, h))
                ret, faces = self._yunet_detector.detect(image)
                if ret and faces is not None and len(faces) > 0:
                    # Pick face with highest confidence (faces[:, -1])
                    best_face = faces[np.argmax(faces[:, -1])]
                    fx, fy, fw, fh = [int(v) for v in best_face[:4]]
                    # Add 12% margin
                    margin_x = int(fw * 0.12)
                    margin_y = int(fh * 0.12)
                    x1 = max(0, fx - margin_x)
                    y1 = max(0, fy - margin_y)
                    x2 = min(w, fx + fw + margin_x)
                    y2 = min(h, fy + fh + margin_y)
                    crop = image[y1:y2, x1:x2]
                    if crop.size > 0:
                        return cv2.resize(crop, self.INPUT_SIZE)
            except Exception as e:
                logger.debug("YuNet detect error: %s", e)

        # Method B: Haar Cascade
        if self._haar_cascade is not None and not self._haar_cascade.empty():
            try:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                faces = self._haar_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(30, 30))
                if len(faces) > 0:
                    # Pick largest face
                    best_face = max(faces, key=lambda b: b[2] * b[3])
                    fx, fy, fw, fh = best_face
                    crop = image[fy:fy + fh, fx:fx + fw]
                    if crop.size > 0:
                        return cv2.resize(crop, self.INPUT_SIZE)
            except Exception as e:
                logger.debug("Haar cascade detect error: %s", e)

        # Method C: If image is already roughly square or portrait face crop, use directly
        aspect = w / float(h)
        if 0.45 <= aspect <= 1.8:
            return cv2.resize(image, self.INPUT_SIZE)

        return None

    def compute_embedding(self, face_image: np.ndarray) -> Optional[np.ndarray]:
        """Computes a 512-D L2-normalized embedding for a face crop."""
        if face_image is None or face_image.size == 0:
            return None

        # Ensure 160x160 RGB
        face_crop = self.detect_face(face_image)
        if face_crop is None:
            face_crop = cv2.resize(face_image, self.INPUT_SIZE)

        if self._resnet is not None:
            try:
                import torch
                rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
                tensor = torch.tensor(rgb).permute(2, 0, 1).float()
                tensor = (tensor - 127.5) / 128.0
                tensor = tensor.unsqueeze(0).to(self._device)

                with torch.no_grad():
                    raw_emb = self._resnet(tensor).cpu().numpy()[0]

                norm = np.linalg.norm(raw_emb)
                if norm > 1e-6:
                    return (raw_emb / norm).astype(np.float32)
                return raw_emb.astype(np.float32)
            except Exception as e:
                logger.error("Error running InceptionResnetV1 embedding: %s", e)

        # Fallback: Spatial color histogram embedding (128-D)
        try:
            hsv = cv2.cvtColor(face_crop, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [8, 16], [0, 180, 0, 256]).flatten()
            norm = np.linalg.norm(hist)
            if norm > 1e-6:
                hist = hist / norm
            # Pad or tile to 512
            full_emb = np.tile(hist, 4)[:512]
            return full_emb.astype(np.float32)
        except Exception as e:
            logger.error("Fallback embedding failed: %s", e)
            return None

    def enroll(self, identity_id: str, name: str, role: str, face_image: np.ndarray, rank_stars: int = 1, rank_title: str = "Officer") -> Optional[np.ndarray]:
        """Enroll one authorized person from a reference photo. Returns the embedding."""
        embedding = self.compute_embedding(face_image)
        if embedding is None:
            logger.warning("FaceVerifier.enroll: No face found in reference photo for %s", name)
            return None

        # Replace existing entry if re-enrolling
        self._enrolled = [e for e in self._enrolled if e.identity_id != identity_id]
        self._enrolled.append(EnrolledIdentity(identity_id, name, role, embedding, rank_stars, rank_title))
        self._rebuild_enrolled_matrix()
        logger.info("FaceVerifier: Successfully enrolled '%s' (%s [%s ⭐], ID: %s)", name, role, rank_stars, identity_id)
        return embedding

    def load_enrolled(self, identities: List[EnrolledIdentity]):
        """Load enrolled identities from persistence."""
        self._enrolled = identities
        self._rebuild_enrolled_matrix()
        logger.info("FaceVerifier: Loaded %d enrolled identities into memory", len(self._enrolled))

    def detect_disguise(self, face_crop: np.ndarray) -> Tuple[bool, float, str]:
        """
        Detects facial coverings, surgical masks, balaclavas, or bandanas.
        Uses dual-hemisphere skin-chroma variance and lower-third occlusion ratio.

        Returns:
            (is_disguised, occlusion_ratio, disguise_type)
        """
        if face_crop is None or face_crop.size == 0 or face_crop.shape[0] < 20 or face_crop.shape[1] < 20:
            return False, 0.0, "NONE"

        try:
            h, w = face_crop.shape[:2]
            upper_face = face_crop[:int(h * 0.45), :]
            lower_face = face_crop[int(h * 0.50):, :]

            # Convert to HSV for skin color segmentation
            hsv_upper = cv2.cvtColor(upper_face, cv2.COLOR_BGR2HSV)
            hsv_lower = cv2.cvtColor(lower_face, cv2.COLOR_BGR2HSV)

            # Standard empirical skin color mask in HSV
            skin_mask_upper = cv2.inRange(hsv_upper, np.array([0, 25, 40], dtype=np.uint8), np.array([25, 220, 255], dtype=np.uint8))
            skin_mask_lower = cv2.inRange(hsv_lower, np.array([0, 25, 40], dtype=np.uint8), np.array([25, 220, 255], dtype=np.uint8))

            upper_skin_ratio = float(np.count_nonzero(skin_mask_upper)) / float(max(1, upper_face.shape[0] * upper_face.shape[1]))
            lower_skin_ratio = float(np.count_nonzero(skin_mask_lower)) / float(max(1, lower_face.shape[0] * lower_face.shape[1]))

            # Lower-face dark fabric check (balaclava / dark mask)
            gray_lower = cv2.cvtColor(lower_face, cv2.COLOR_BGR2GRAY)
            dark_fabric_ratio = float(np.count_nonzero(gray_lower < 55)) / float(max(1, lower_face.shape[0] * lower_face.shape[1]))

            # Medical blue/cyan mask check
            blue_mask = cv2.inRange(hsv_lower, np.array([85, 40, 50], dtype=np.uint8), np.array([130, 255, 255], dtype=np.uint8))
            blue_mask_ratio = float(np.count_nonzero(blue_mask)) / float(max(1, lower_face.shape[0] * lower_face.shape[1]))

            if upper_skin_ratio > 0.18:
                if blue_mask_ratio > 0.22:
                    return True, round(blue_mask_ratio, 2), "SURGICAL_MASK"
                elif dark_fabric_ratio > 0.35 and lower_skin_ratio < 0.15:
                    return True, round(dark_fabric_ratio, 2), "BALACLAVA_OR_DARK_WRAP"
                elif lower_skin_ratio < 0.12 and (upper_skin_ratio / max(0.01, lower_skin_ratio) > 3.0):
                    return True, round(1.0 - lower_skin_ratio, 2), "FACIAL_COVERING"

            return False, 0.0, "NONE"
        except Exception as e:
            logger.debug("Disguise detection calculation error: %s", e)
            return False, 0.0, "NONE"

    def verify(self, face_crop: np.ndarray) -> VerificationResult:
        """
        Matches a query crop against the enrolled database.
        Returns VerificationResult with status, identity_id, name, and similarity confidence.
        """
        # Pre-check for mask / disguise occlusion
        is_disguised, occ_ratio, disguise_type = self.detect_disguise(face_crop)
        if is_disguised:
            return VerificationResult(
                status=VerificationStatus.DISGUISE_DETECTED,
                identity_id=None,
                name=f"Covered Face ({disguise_type})",
                confidence=occ_ratio,
                is_disguised=True,
                disguise_type=disguise_type,
            )

        if not self._enrolled or self._enrolled_matrix is None:
            return VerificationResult(VerificationStatus.UNKNOWN, None, None, 0.0)

        query_emb = self.compute_embedding(face_crop)
        if query_emb is None:
            return VerificationResult(VerificationStatus.NO_FACE_DETECTED, None, None, 0.0)

        # Fast cosine similarity via dot product against normalized matrix (N, 512)
        similarities = np.dot(self._enrolled_matrix, query_emb)
        best_idx = int(np.argmax(similarities))
        best_similarity = float(similarities[best_idx])
        best_match = self._enrolled[best_idx]

        # Map raw cosine similarity [0.60, 0.90] to intuitive [0.0, 1.0] confidence score
        confidence = max(0.0, min(1.0, (best_similarity - 0.60) / 0.30))

        if best_similarity >= self.MATCH_THRESHOLD:
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                identity_id=best_match.identity_id,
                name=best_match.name,
                confidence=confidence,
                role=best_match.role,
                rank_stars=getattr(best_match, "rank_stars", 1),
                rank_title=getattr(best_match, "rank_title", "Officer"),
            )
        elif best_similarity >= self.LOW_CONFIDENCE_THRESHOLD:
            return VerificationResult(
                status=VerificationStatus.LOW_CONFIDENCE,
                identity_id=best_match.identity_id,
                name=best_match.name,
                confidence=confidence,
                role=best_match.role,
                rank_stars=getattr(best_match, "rank_stars", 1),
                rank_title=getattr(best_match, "rank_title", "Officer"),
            )
        else:
            return VerificationResult(
                status=VerificationStatus.UNKNOWN,
                identity_id=None,
                name=None,
                confidence=confidence,
            )
