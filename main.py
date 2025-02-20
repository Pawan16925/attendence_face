import cv2
import numpy as np
import face_recognition
import os
import pandas as pd
import logging
import argparse
from datetime import datetime
from typing import List, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('attendance_log.txt'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
CONFIG = {
    'TRAINING_IMAGES_PATH': 'Training_images',
    'ATTENDANCE_FILE': 'Attendance.csv',
    'CONFIDENCE_THRESHOLD': 0.5,  # Lower means more strict face matching
    'RESIZE_SCALE': 0.25,
    'WEBCAM_INDEX': 0,
}

def load_training_images(path: str) -> Tuple[List[np.ndarray], List[str], List[str]]:
    """
    Load training images and extract names and roll numbers.
    
    Args:
        path (str): Directory containing training images
    
    Returns:
        Tuple of images, names, and roll numbers
    """
    images = []
    class_names = []
    roll_numbers = []
    
    try:
        image_files = os.listdir(path)
        logger.info(f"Found {len(image_files)} training images")
        
        for filename in image_files:
            img_path = os.path.join(path, filename)
            try:
                cur_img = cv2.imread(img_path)
                if cur_img is not None:
                    # Split filename to extract roll number and name
                    name_parts = os.path.splitext(filename)[0].split('_')
                    
                    # Check if first part is a roll number (digits)
                    if name_parts[0].isdigit():
                        roll_no = name_parts[0]
                        name = ' '.join(name_parts[1:]).title()
                    else:
                        roll_no = 'N/A'
                        name = ' '.join(name_parts).title()
                    
                    images.append(cur_img)
                    class_names.append(name)
                    roll_numbers.append(roll_no)
                else:
                    logger.warning(f"Could not load image: {img_path}")
            except Exception as e:
                logger.error(f"Error loading {filename}: {e}")
        
        return images, class_names, roll_numbers
    
    except Exception as e:
        logger.critical(f"Failed to load training images: {e}")
        return [], [], []

def find_encodings(images: List[np.ndarray]) -> List[np.ndarray]:
    """
    Encode known faces.
    
    Args:
        images (List[np.ndarray]): List of training images
    
    Returns:
        List of face encodings
    """
    encode_list = []
    for img in images:
        try:
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            encodings = face_recognition.face_encodings(img_rgb)
            
            if encodings:
                encode_list.append(encodings[0])
            else:
                logger.warning("No face detected in an image")
        except Exception as e:
            logger.error(f"Error encoding image: {e}")
    
    return encode_list

def mark_attendance(name: str, roll_no: str, attendance_file: str):
    """
    Mark or update attendance for a recognized person.
    
    Args:
        name (str): Name of the recognized person
        roll_no (str): Roll number of the recognized person
        attendance_file (str): Path to attendance CSV file
    """
    try:
        # Check if CSV exists, if not create with new columns
        try:
            df = pd.read_csv(attendance_file)
        except FileNotFoundError:
            df = pd.DataFrame(columns=["Name", "RollNo", "Date", "Time"])

        now = datetime.now()
        date_string = now.strftime('%Y-%m-%d')
        time_string = now.strftime('%H:%M:%S')

        # Check for existing entry on the same day
        mask = (df["Name"] == name) & (df["Date"] == date_string)
        
        if mask.any():
            # Update time if already present
            df.loc[mask, "Time"] = time_string
            logger.info(f"Updated attendance for {name} (Roll No: {roll_no})")
        else:
            # Add new entry
            new_entry = pd.DataFrame([[name, roll_no, date_string, time_string]], 
                                     columns=["Name", "RollNo", "Date", "Time"])
            df = pd.concat([df, new_entry], ignore_index=True)
            logger.info(f"Marked attendance for {name} (Roll No: {roll_no})")

        df.to_csv(attendance_file, index=False)
    except Exception as e:
        logger.error(f"Error marking attendance: {e}")

def recognize_faces(
    config: dict, 
    known_encodings: List[np.ndarray], 
    known_names: List[str],
    known_roll_nos: List[str]
):
    """
    Main face recognition and attendance marking function.
    
    Args:
        config (dict): Configuration dictionary
        known_encodings (List[np.ndarray]): Pre-computed face encodings
        known_names (List[str]): Names corresponding to encodings
        known_roll_nos (List[str]): Roll numbers corresponding to encodings
    """
    cap = cv2.VideoCapture(config['WEBCAM_INDEX'])
    
    if not cap.isOpened():
        logger.critical("Cannot open webcam")
        return

    try:
        while True:
            success, frame = cap.read()
            
            if not success:
                logger.warning("Failed to grab frame")
                break

            # Resize frame for faster processing
            small_frame = cv2.resize(frame, (0, 0), None, 
                                     config['RESIZE_SCALE'], 
                                     config['RESIZE_SCALE'])
            small_frame_rgb = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            # Find faces in current frame
            face_locations = face_recognition.face_locations(small_frame_rgb)
            face_encodings = face_recognition.face_encodings(small_frame_rgb, face_locations)

            for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                # Scale back to original frame size
                top = int(top / config['RESIZE_SCALE'])
                right = int(right / config['RESIZE_SCALE'])
                bottom = int(bottom / config['RESIZE_SCALE'])
                left = int(left / config['RESIZE_SCALE'])

                # Compare face with known faces
                matches = face_recognition.compare_faces(
                    known_encodings, 
                    face_encoding, 
                    tolerance=config['CONFIDENCE_THRESHOLD']
                )
                name = "Unknown"
                roll_no = "N/A"

                face_distances = face_recognition.face_distance(known_encodings, face_encoding)
                best_match_index = np.argmin(face_distances)

                if matches[best_match_index]:
                    name = known_names[best_match_index].upper()
                    roll_no = known_roll_nos[best_match_index]
                    mark_attendance(name, roll_no, config['ATTENDANCE_FILE'])

                # Draw rectangle and name
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.rectangle(frame, (left, bottom - 35), (right, bottom), (0, 255, 0), cv2.FILLED)
                cv2.putText(frame, f"{name} ({roll_no})", (left + 6, bottom - 6), 
                            cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 255), 2)

            cv2.imshow('Face Recognition Attendance', frame)
            
            # Exit on 'q' key press
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except Exception as e:
        logger.error(f"Error in face recognition: {e}")
    
    finally:
        cap.release()
        cv2.destroyAllWindows()

def main():
    """
    Main execution function with argument parsing.
    """
    parser = argparse.ArgumentParser(description='Face Recognition Attendance System')
    parser.add_argument('--train', action='store_true', help='Train the face recognition model')
    args = parser.parse_args()

    # Load training images
    training_images, class_names, roll_numbers = load_training_images(CONFIG['TRAINING_IMAGES_PATH'])
    
    if not training_images:
        logger.critical("No training images found. Please upload student images.")
        return

    # Compute face encodings
    known_encodings = find_encodings(training_images)

    if args.train:
        logger.info("Training completed. Encodings generated.")
        return

    # Start face recognition
    recognize_faces(CONFIG, known_encodings, class_names, roll_numbers)

if __name__ == '__main__':
    main()
