import os
import shutil
import csv
import json
import re
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename
import logging

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # For flash messages

UPLOAD_FOLDER = 'Training_images'
STATIC_FOLDER = 'static/Training_images'
ATTENDANCE_FILE = 'Attendance.csv'
STATS_FILE = 'attendance_stats.json'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['STATIC_FOLDER'] = STATIC_FOLDER
app.config['ATTENDANCE_FILE'] = ATTENDANCE_FILE
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB file size limit

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)

def get_image_files(directory):
    """
    Get all image files from the specified directory.
    Supports common image file extensions.
    """
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'}
    return [
        f for f in os.listdir(directory) 
        if os.path.isfile(os.path.join(directory, f)) 
        and os.path.splitext(f)[1].lower() in image_extensions
    ]

def get_student_details():
    """
    Get student details from image filenames in Training_images.
    
    Returns a list of dictionaries with student information:
    - name: extracted from filename
    - image: filename of the image
    - roll_no: extracted from filename (assuming format like RollNo_Name.jpg)
    """
    students = []
    images = get_image_files(UPLOAD_FOLDER)
    
    for image in images:
        # Split filename into parts
        parts = os.path.splitext(image)[0].split('_')
        
        # Check if the first part looks like a roll number (all digits)
        if parts[0].isdigit():
            roll_no = parts[0]
            name = ' '.join(parts[1:]).title()
        else:
            # If no roll number found, use a placeholder or empty string
            roll_no = 'N/A'
            name = os.path.splitext(image)[0].replace('_', ' ').title()
        
        students.append({
            'name': name,
            'image': image,
            'roll_no': roll_no
        })
    
    return students

def read_attendance_data():
    """
    Read attendance data from CSV file.
    """
    attendance_data = []
    try:
        with open(ATTENDANCE_FILE, 'r') as csvfile:
            csvreader = csv.DictReader(csvfile)
            attendance_data = list(csvreader)
            # Sort by date and time in descending order
            attendance_data.sort(key=lambda x: (x['Date'], x['Time']), reverse=True)
    except FileNotFoundError:
        print(f"Attendance file {ATTENDANCE_FILE} not found.")
    except Exception as e:
        print(f"Error reading attendance file: {e}")
    
    return attendance_data

def write_attendance_data(attendance_data):
    """
    Write attendance data to CSV file.
    """
    try:
        with open(ATTENDANCE_FILE, 'w', newline='') as csvfile:
            fieldnames = ['Name', 'Date', 'Time']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(attendance_data)
    except Exception as e:
        print(f"Error writing to attendance file: {e}")

def update_attendance_stats(name):
    """
    Update and maintain attendance statistics.
    """
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r') as f:
                stats = json.load(f)
        else:
            stats = {}

        today = datetime.now().strftime('%Y-%m-%d')
        
        if name not in stats:
            stats[name] = {
                'total_days': 1,
                'first_attendance': today,
                'last_attendance': today,
                'consecutive_days': 1
            }
        else:
            stats[name]['total_days'] += 1
            stats[name]['last_attendance'] = today
            
            # Check consecutive days
            last_date = datetime.strptime(stats[name]['last_attendance'], '%Y-%m-%d')
            if last_date.date() == (datetime.now().date() - timedelta(days=1)):
                stats[name]['consecutive_days'] += 1
            else:
                stats[name]['consecutive_days'] = 1

        with open(STATS_FILE, 'w') as f:
            json.dump(stats, f, indent=4)
    except Exception as e:
        print(f"Error updating attendance stats: {e}")

def update_student_references(old_name, old_roll_no, new_name, new_roll_no, old_filename, new_filename):
    """
    Comprehensively update student references across multiple files.
    
    Args:
        old_name (str): Original student name
        old_roll_no (str): Original student roll number
        new_name (str): Updated student name
        new_roll_no (str): Updated student roll number
        old_filename (str): Original image filename
        new_filename (str): Updated image filename
    """
    try:
        # Update Attendance CSV
        attendance_updated = False
        with open(ATTENDANCE_FILE, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            attendance_data = list(reader)
        
        for record in attendance_data:
            if record['Name'] == old_name and record['RollNo'] == old_roll_no:
                record['Name'] = new_name
                record['RollNo'] = new_roll_no
                record['Image'] = new_filename
                attendance_updated = True
        
        if attendance_updated:
            with open(ATTENDANCE_FILE, 'w', newline='') as csvfile:
                fieldnames = attendance_data[0].keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(attendance_data)
        
        # Rename image files in Training_images and static folders
        old_upload_path = os.path.join(UPLOAD_FOLDER, old_filename)
        old_static_path = os.path.join(STATIC_FOLDER, old_filename)
        
        new_upload_path = os.path.join(UPLOAD_FOLDER, new_filename)
        new_static_path = os.path.join(STATIC_FOLDER, new_filename)
        
        # Rename files if they exist
        if os.path.exists(old_upload_path):
            os.rename(old_upload_path, new_upload_path)
        
        if os.path.exists(old_static_path):
            os.rename(old_static_path, new_static_path)
        
        # Optional: Log the update
        logging.info(f"Updated student: {old_name} (Roll No: {old_roll_no}) -> {new_name} (Roll No: {new_roll_no})")
    
    except Exception as e:
        logging.error(f"Error updating student references: {e}")
        raise

@app.route('/')
def index():
    """
    Render index page with overall statistics.
    """
    # Calculate total attendees from Training_images folder
    total_attendees = len(get_image_files(UPLOAD_FOLDER))

    # Calculate today's attendance from Attendance.csv
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Read attendance data directly from CSV
    today_attendees = 0
    try:
        with open(ATTENDANCE_FILE, 'r') as csvfile:
            csvreader = csv.DictReader(csvfile)
            today_attendees = sum(1 for record in csvreader if record['Date'] == today)
    except FileNotFoundError:
        today_attendees = 0
    except Exception as e:
        print(f"Error reading attendance file: {e}")
        today_attendees = 0

    # Get student details
    students = get_student_details()

    return render_template('index.html', 
                           total_attendees=total_attendees, 
                           today_attendees=today_attendees,
                           students=students)

@app.route('/upload_students')
def upload_students():
    """
    Render upload students page with image gallery.
    Includes student details with roll numbers.
    """
    images = get_image_files(UPLOAD_FOLDER)
    
    # Get student details to map images to roll numbers and names
    students = get_student_details()
    student_details = {student['image']: student for student in students}
    
    # Augment images with student details
    image_details = []
    for image in images:
        details = student_details.get(image, {
            'name': image.split('.')[0].replace('_', ' ').title(),
            'roll_no': 'N/A'
        })
        image_details.append({
            'filename': image,
            'name': details['name'],
            'roll_no': details.get('roll_no', 'N/A')
        })
    
    return render_template('upload_students.html', 
                           images=image_details)

@app.route('/upload', methods=['POST'])
def upload():
    """
    Handle student/employee image upload.
    Creates a filename with roll number and name.
    """
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('upload_students'))
    
    file = request.files['file']
    name = request.form.get('name', '').strip()
    rollno = request.form.get('rollno', '').strip()
    
    # Validate inputs
    if not name or not rollno:
        flash('Name and Roll Number are required', 'danger')
        return redirect(url_for('upload_students'))
    
    # Validate name (letters and spaces only)
    if not re.match(r'^[A-Za-z\s]+$', name):
        flash('Invalid name format', 'danger')
        return redirect(url_for('upload_students'))
    
    # Validate roll number (digits only)
    if not re.match(r'^[0-9]+$', rollno):
        flash('Invalid roll number format', 'danger')
        return redirect(url_for('upload_students'))
    
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('upload_students'))
    
    if file:
        # Sanitize filename
        filename = secure_filename(file.filename)
        file_ext = os.path.splitext(filename)[1]
        
        # Create new filename with roll number and name
        new_filename = f"{rollno}_{name.replace(' ', '_')}{file_ext}"
        
        # Save to Training_images
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
        file.save(file_path)
        
        # Copy to static folder for web display
        static_path = os.path.join(app.config['STATIC_FOLDER'], new_filename)
        shutil.copy(file_path, static_path)
        
        flash('Image uploaded successfully!', 'success')
        return redirect(url_for('upload_students'))

@app.route('/delete_image/<filename>', methods=['POST'])
def delete_image(filename):
    """
    Delete an image from Training_images and static/Training_images
    """
    try:
        # Remove from Training_images
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        static_file_path = os.path.join(app.config['STATIC_FOLDER'], filename)
        
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(static_file_path):
            os.remove(static_file_path)
        
        flash(f"Image {filename} deleted successfully!", 'success')
    except Exception as e:
        flash(f"Error deleting image: {str(e)}", 'error')
    
    return redirect(url_for('upload_students'))

@app.route('/attendance')
def attendance_records():
    """
    Render attendance records page with attendance log and statistics.
    Supports filtering attendance records by date.
    """
    # Get the date filter from query parameter, default to today's date
    selected_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    today_date = datetime.now().strftime('%Y-%m-%d')

    # Read attendance data from CSV
    attendance_data = read_attendance_data()

    # Filter attendance records by selected date
    filtered_attendance = [
        record for record in attendance_data 
        if record['Date'] == selected_date
    ]

    # Calculate attendance statistics
    total_students = len(get_student_details())
    attended_count = len(filtered_attendance)
    absent_count = total_students - attended_count
    attendance_percentage = round((attended_count / total_students * 100), 2) if total_students > 0 else 0

    stats = {
        'total_students': total_students,
        'attended_count': attended_count,
        'absent_count': absent_count,
        'attendance_percentage': attendance_percentage
    }

    return render_template('attendance.html', 
                           attendance=filtered_attendance, 
                           stats=stats,
                           selected_date=selected_date,
                           today_date=today_date)

@app.route('/download_attendance')
def download_attendance():
    """
    Download the Attendance.csv file.
    
    Returns:
        A downloadable CSV file with attendance records
    """
    try:
        # Ensure the file exists
        if not os.path.exists(ATTENDANCE_FILE):
            flash('Attendance file not found', 'danger')
            return redirect(url_for('attendance_records'))
        
        # Generate a filename with current date
        today = datetime.now().strftime('%Y-%m-%d')
        download_filename = f'Attendance_{today}.csv'
        
        return send_file(
            ATTENDANCE_FILE, 
            as_attachment=True, 
            download_name=download_filename,
            mimetype='text/csv'
        )
    except Exception as e:
        print(f"Error downloading attendance file: {e}")
        flash('Error downloading attendance file', 'danger')
        return redirect(url_for('attendance_records'))

@app.route('/manage_students')
def manage_students():
    """
    Render manage students page with list of students and their details.
    """
    # Get student details with their images
    students = get_student_details()
    
    # Augment student details with full image path
    for student in students:
        student['image_path'] = os.path.join('Training_images', student['image'])
    
    return render_template('manage_students.html', students=students)

@app.route('/edit_student', methods=['POST'])
def edit_student():
    """
    Edit student details comprehensively.
    Updates name, roll number, and optionally image.
    """
    try:
        # Get form data
        old_filename = request.form.get('old_filename')
        new_name = request.form.get('name').strip()
        new_roll_no = request.form.get('rollno').strip()
        
        # Validate inputs
        if not new_name or not new_roll_no:
            flash('Name and Roll No cannot be empty', 'danger')
            return redirect(url_for('manage_students'))
        
        # Extract old name and roll no from the filename
        old_name_match = re.match(r'(\d+)_([^.]+)', old_filename)
        if old_name_match:
            old_roll_no, old_name = old_name_match.groups()
            old_name = old_name.replace('_', ' ')
        else:
            flash('Invalid student filename format', 'danger')
            return redirect(url_for('manage_students'))
        
        # Generate new filename
        file_ext = os.path.splitext(old_filename)[1]
        new_filename = f"{new_roll_no}_{new_name.replace(' ', '_')}{file_ext}"
        
        # Check if file is uploaded
        file = request.files.get('file')
        if file and file.filename:
            # Validate file
            if not allowed_file(file.filename):
                flash('Invalid file type. Please upload an image.', 'danger')
                return redirect(url_for('manage_students'))
            
            # Remove old files
            old_filepath = os.path.join(UPLOAD_FOLDER, old_filename)
            old_static_filepath = os.path.join(STATIC_FOLDER, old_filename)
            
            if os.path.exists(old_filepath):
                os.remove(old_filepath)
            if os.path.exists(old_static_filepath):
                os.remove(old_static_filepath)
            
            # Save new file
            new_filepath = os.path.join(UPLOAD_FOLDER, new_filename)
            new_static_filepath = os.path.join(STATIC_FOLDER, new_filename)
            
            file.save(new_filepath)
            shutil.copy(new_filepath, new_static_filepath)
        
        # Update references across files
        update_student_references(
            old_name, old_roll_no, 
            new_name, new_roll_no, 
            old_filename, new_filename
        )
        
        flash('Student details updated successfully', 'success')
        return redirect(url_for('manage_students'))

    except Exception as e:
        flash(f'Error updating student: {str(e)}', 'danger')
        return redirect(url_for('manage_students'))

@app.route('/delete_student', methods=['POST'])
def delete_student():
    """
    Delete a student's image and details.
    """
    try:
        filename = request.form.get('filename')
        
        # Delete from Training_images
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        
        # Delete from static/Training_images
        static_filepath = os.path.join(STATIC_FOLDER, filename)
        if os.path.exists(static_filepath):
            os.remove(static_filepath)

        flash('Student image deleted successfully', 'success')
        return redirect(url_for('manage_students'))

    except Exception as e:
        flash(f'Error deleting student: {str(e)}', 'danger')
        return redirect(url_for('manage_students'))

@app.route('/update_student_image', methods=['POST'])
def update_student_image():
    """
    Update a student's image while preserving name and roll number.
    """
    try:
        # Get form data
        old_filename = request.form.get('old_filename')
        name = request.form.get('name')
        roll_no = request.form.get('rollno')
        
        # Check if file is uploaded
        if 'file' not in request.files:
            flash('No file uploaded', 'danger')
            return redirect(url_for('manage_students'))
        
        file = request.files['file']
        
        # Check if filename is empty
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(url_for('manage_students'))
        
        # Validate file type
        if not allowed_file(file.filename):
            flash('Invalid file type. Please upload an image.', 'danger')
            return redirect(url_for('manage_students'))
        
        # Generate new filename
        file_ext = os.path.splitext(file.filename)[1]
        new_filename = f"{roll_no}_{name.replace(' ', '_')}{file_ext}"
        
        # Remove old files
        old_filepath = os.path.join(UPLOAD_FOLDER, old_filename)
        old_static_filepath = os.path.join(STATIC_FOLDER, old_filename)
        
        if os.path.exists(old_filepath):
            os.remove(old_filepath)
        if os.path.exists(old_static_filepath):
            os.remove(old_static_filepath)
        
        # Save new file
        new_filepath = os.path.join(UPLOAD_FOLDER, new_filename)
        new_static_filepath = os.path.join(STATIC_FOLDER, new_filename)
        
        file.save(new_filepath)
        shutil.copy(new_filepath, new_static_filepath)
        
        flash('Student image updated successfully', 'success')
        return redirect(url_for('manage_students'))
    
    except Exception as e:
        flash(f'Error updating student image: {str(e)}', 'danger')
        return redirect(url_for('manage_students'))

def allowed_file(filename):
    """
    Check if the uploaded file is an allowed image type.
    """
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

if __name__ == '__main__':
    app.run(debug=True)
