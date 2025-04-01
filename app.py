from flask import Flask, render_template, request, redirect, url_for, session, make_response
from flask_sqlalchemy import SQLAlchemy
from PIL import Image
import os
import uuid
import webbrowser
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
import pdfkit

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz.db'
app.config['SECRET_KEY'] = os.urandom(24)  # Sicherer Zufallsschlüssel
db = SQLAlchemy(app)

# Bildzuordnung
IMAGE_TERMS = {
    '1': 'Rechteckig',
    '2': 'Quadratisch',
    '3': 'L-förmig',
    '4': 'Rund'
}

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    module = db.Column(db.String(20), nullable=False)
    text = db.Column(db.String(200), nullable=False)
    subtitle = db.Column(db.String(200), nullable=True)
    answers = db.relationship('Answer', backref='question', lazy=True)
    image = db.Column(db.String(200), nullable=True)

class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    text = db.Column(db.String(200), nullable=True)
    score = db.Column(db.Integer, nullable=True)

def get_questions(module):
    return Question.query.filter_by(module=module).all()

def calculate_module_score(answers):
    module_score = 0
    for question_id, answer in answers.items():
        if isinstance(answer, dict) and answer.get('score') is not None:
            module_score += answer['score']
    return module_score

def resize_image(image_path, size=(300, 300)):
    with Image.open(image_path) as img:
        img.thumbnail(size, Image.LANCZOS)
        img.save(image_path, quality=95, optimize=True)

@app.route('/')
def index():
    return redirect(url_for('info'))

@app.route('/info', methods=['GET', 'POST'])
def info():
    session.clear()
    if request.method == 'POST':
        return redirect(url_for('basic_quiz'))
    return render_template('info.html')

@app.route('/basic_quiz/', methods=['GET', 'POST'])
def basic_quiz():
    module = 'Basic'
    questions = get_questions(module)
    total_questions = len(questions)

    if 'question_index' not in session or session.get('module') != module:
        session['question_index'] = 0
        session['answers'] = {}
        session['module'] = module

    question_index = session['question_index']

    if request.method == 'POST':
        question = questions[question_index]
        answer_id = request.form.get('answer')
        free_text = request.form.get('free_text')

        if answer_id:
            answer = Answer.query.get(answer_id)
            session['answers'][str(question.id)] = {'text': answer.text, 'score': answer.score}
        elif free_text:
            session['answers'][str(question.id)] = {'text': free_text, 'score': None}

        session['question_index'] += 1
        if session['question_index'] >= total_questions:
            session['basic_answers'] = session['answers']
            return redirect(url_for('choose_module'))

        return redirect(url_for('basic_quiz'))

    if questions and question_index < len(questions):
        question = questions[question_index]
        return render_template('basic_quiz.html', module=module, question=question,
                               question_index=question_index, total_questions=total_questions)

    return render_template('error.html', message="Ein unerwarteter Fehler ist aufgetreten.")

@app.route('/choose_module/', methods=['GET', 'POST'])
def choose_module():
    if request.method == 'POST':
        selected_module = request.form.get('module')
        return redirect(url_for('quiz', module=selected_module))
    return render_template('choose_module.html')

@app.route('/quiz/<module>', methods=['GET', 'POST'])
def quiz(module):
    questions = get_questions(module)
    total_questions = len(questions)

    if 'question_index' not in session or session.get('module') != module:
        session['question_index'] = 0
        session['answers'] = {}
        session['module'] = module

    question_index = session['question_index']

    if request.method == 'POST':
        question = questions[question_index]
        answer_data = {}

        if question.answers:
            answer_id = request.form.get('answer')
            answer = Answer.query.get(answer_id)
            
            # Spezialbehandlung für Bildfrage
            if "Welche Form oder Kontur gleicht dein Gebäude am ehesten?" in question.text:
                bild_nummer = answer.text.split()[-1]
                answer_data['text'] = IMAGE_TERMS.get(bild_nummer, 'Unbekannte Form')
            else:
                answer_data['text'] = answer.text
                
            answer_data['score'] = answer.score
        else:
            answer_data['text'] = request.form.get('free_text')
            answer_data['score'] = None

        session['answers'][str(question.id)] = answer_data
        session['question_index'] += 1

        if session['question_index'] >= total_questions:
            session[f'{module.lower()}_answers'] = session['answers']
            return redirect(url_for('summary'))
            
        return redirect(url_for('quiz', module=module))

    question = questions[question_index]
    return render_template(
        f'{module.lower()}_quiz.html',
        question=question,
        question_index=question_index,
        total_questions=total_questions,
        image_terms=IMAGE_TERMS
    )


@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'image' in request.files:
        image = request.files['image']
        if image.filename != '':
            image_path = os.path.join(app.config['static/images'], image.filename)
            image.save(image_path)
            resize_image(image_path)
            return 'Image uploaded and resized successfully'
    return 'No image uploaded', 400

@app.route('/summary/')
def summary():
    basic_answers = session.get('basic_answers', {})
    express_answers = session.get('express_answers', {})
    advanced_answers = session.get('advanced_answers', {})
    
    all_answers = {
        'Basic': basic_answers,
        'Express': express_answers,
        'Advanced': advanced_answers,
    }
    
    module_scores = {
        'Basic': calculate_module_score(basic_answers),
        'Express': calculate_module_score(express_answers),
        'Advanced': calculate_module_score(advanced_answers),
    }
    
    total_score = sum(module_scores.values())
    
    # Speichern der Daten in der Session für den PDF-Export
    session['all_answers'] = all_answers
    session['module_scores'] = module_scores
    session['total_score'] = total_score
    
    questions = {str(q.id): q for q in Question.query.all()}
    
    return render_template(
        'summary.html',
        all_answers=all_answers,
        module_scores=module_scores,
        total_score=total_score,
        questions=questions
    )

@app.route('/download_pdf', methods=['GET'])
def download_pdf():
    # Daten aus der Session abrufen
    all_answers = session.get('all_answers', {})
    module_scores = session.get('module_scores', {})
    total_score = session.get('total_score', 0)
    questions = {str(q.id): q for q in Question.query.all()}  # Fragen aus der Datenbank

    # BytesIO-Objekt für das PDF erstellen
    pdf_buffer = BytesIO()
    pdf = SimpleDocTemplate(pdf_buffer, pagesize=letter)

    # Elemente für das PDF sammeln
    elements = []

    # Titel hinzufügen
    styles = getSampleStyleSheet()
    title = [["Sanierungsbewertung - Zusammenfassung"]]
    title_table = Table(title)
    title_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 16),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ]))
    elements.append(title_table)

    # Gesamtscore hinzufügen
    total_score_data = [[f"Gesamtscore: {total_score} Punkte"]]
    total_score_table = Table(total_score_data)
    total_score_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
    ]))
    elements.append(total_score_table)

    # Module und Fragen/Antworten hinzufügen
    for module, answers in all_answers.items():
        # Modultitel hinzufügen
        module_title = [[f"{module} Modul"]]
        module_table = Table(module_title)
        module_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ]))
        elements.append(module_table)

        # Tabelle mit Fragen/Antworten/Scores erstellen
        data = [["Frage", "Antwort", "Punkte"]]
        
        for question_id, answer in answers.items():
            question_text = questions.get(question_id).text if question_id in questions else "Unbekannte Frage"
            answer_text = answer.get('text', 'Keine Antwort')
            score_text = str(answer.get('score', ''))

            # Verwenden Sie Paragraphs für Zeilenumbruch
            question_paragraph = Paragraph(question_text, styles["Normal"])
            answer_paragraph = Paragraph(answer_text, styles["Normal"])
            
            data.append([question_paragraph, answer_paragraph, score_text])

        table = Table(data, colWidths=[250, 150, 100])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (1, 1), (-2, -2), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1.5, colors.black),
        ]))
        elements.append(table)

        # Abstand zwischen Modulen einfügen
        elements.append(Spacer(1, 40))  

    # PDF erstellen und zurückgeben
    pdf.build(elements)
    pdf_buffer.seek(0)
    
    response = make_response(pdf_buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=sanierungsbewertung.pdf'
    
    return response



def populate_database():
    db.session.execute(Answer.__table__.delete())
    db.session.execute(Question.__table__.delete())
    db.session.commit()
    
    # Basic Modul
    q1 = Question(module="Basic", text="Projektname")
    q2 = Question(module="Basic", text="Standort")
    q3 = Question(module="Basic", text="Wer ist Eigentümer des Gebäudes?")
    a3_1 = Answer(question=q3, text="Privatperson", score=3)
    a3_2 = Answer(question=q3, text="Unternehmen", score=4)
    a3_3 = Answer(question=q3, text="Öffentliche Hand", score=2)
    a3_4 = Answer(question=q3, text="Gesellschaft", score=4)
    a3_5 = Answer(question=q3, text="Sonstiges", score=5)

    q4 = Question(module="Basic", text="Baujahr")
    a4_1 = Answer(question=q4, text="Vor 1950", score=6)
    a4_2 = Answer(question=q4, text="1950-1970", score=6)
    a4_3 = Answer(question=q4, text="1970-1990", score=8)
    a4_4 = Answer(question=q4, text="Nach 1990", score=9)

    q5 = Question(module="Basic", text="Gebäudetyp")
    a5_1 = Answer(question=q5, text="Wohngebäude", score=2)
    a5_2 = Answer(question=q5, text="Gewerbegebäude", score=3)
    a5_3 = Answer(question=q5, text="Gemischt genutztes Gebäude", score=4)
    a5_4 = Answer(question=q5, text="Sonstiges", score=6)

    q6 = Question(module="Basic", text="Zweck der Sanierung?")
    a6_1 = Answer(question=q6, text="Energetische Verbesserung", score=7)
    a6_2 = Answer(question=q6, text="Ästhetische Aufwertung", score=7)
    a6_3 = Answer(question=q6, text="Umnutzung", score=5)

    # Express Modul
    q7 = Question(module="Express", text="Welche Form oder Kontur gleicht dein Gebäude am ehesten?", image="question_7.jpg")
    a7_1 = Answer(question=q7, text="Bild 1", score=3)
    a7_2 = Answer(question=q7, text="Bild 2", score=2)
    a7_3 = Answer(question=q7, text="Bild 3", score=1)
    a7_4 = Answer(question=q7, text="Bild 4", score=0)

    q8 = Question(module="Express", text="Stammt das Gebäude aus dem Zeitraum zwischen 1950 und 1979 (energetisch schlecht aber strukturell gut geeignet)?")
    a8_1 = Answer(question=q8, text="Ja (1950-1979)", score=2)
    a8_2 = Answer(question=q8, text="Teilweise (1980-1999)", score=1)
    a8_3 = Answer(question=q8, text="Nein (vor 1950 oder nach 2000)", score=0)

    q9 = Question(module="Express", text="Ist die vorhandene Gebäudetechnik (Heizung, Wasserleitungen) sanierungsbedürftig?")
    a9_1 = Answer(question=q9, text="Ja", score=4)
    a9_2 = Answer(question=q9, text="Teilweise", score=2)
    a9_3 = Answer(question=q9, text="Nein", score=0)

    q10 = Question(module="Express", text="Fällt das Gebäude unter den Denkmalschutz?")
    a10_1 = Answer(question=q10, text="Ja", score=0)
    a10_2 = Answer(question=q10, text="Nein", score=10)

    q11 = Question(module="Express", text="Verfolgt der Eigentümer langfristige Ziele mit dem Objekt?")
    a11_1 = Answer(question=q11, text="Ja Bestandserhaltung langfristige Nutzung", score=2)
    a11_2 = Answer(question=q11, text="Unklar keine klare Strategie erkennbar", score=1)
    a11_3 = Answer(question=q11, text="Kurzfristige Renditeorientierung", score=0)

    q12 = Question(module="Express", text="Erweiterungspotential: Gibt es Möglichkeiten/Potential für Aufstockungen oder Wohnraumerweiterungen?")
    a12_1 = Answer(question=q12, text="Ja deutliches Potential vorhanden", score=2)
    a12_2 = Answer(question=q12, text="Prüffähig unklar", score=1)
    a12_3 = Answer(question=q12, text="Nein kein Potential", score=0)

    q13 = Question(module="Express", text="Gibt es Wiederholungsfaktoren im Gebäude oder den Gebäuden?")
    a13_1 = Answer(question=q13, text="Ja die Gebäude sind gleich aufgebaut", score=8)
    a13_2 = Answer(question=q13, text="Teilweise die Stockwerke/Wohneinheiten sind ähnlich", score=4)
    a13_3 = Answer(question=q13, text="Nein es gibt keine oder nur geringe Wiederholungsfaktoren", score=0)


    # Advanced Modul
    q14 = Question(module="Advanced", text="Ist die Gebäudeform klar und strukturiert?", subtitle="Gebäudestruktur und Kubatur")
    a14_1 = Answer(question=q14, text="Ja", score=2)
    a14_2 = Answer(question=q14, text="Nein", score=0)
    a14_3 = Answer(question=q14, text="Teilweise", score=1)

    q15 = Question(module="Advanced", text="Welche Gebäudehöhe hat das Objekt?", subtitle="Gebäudestruktur und Kubatur")
    a15_1 = Answer(question=q15, text="<13m", score=1)
    a15_2 = Answer(question=q15, text="13–22m", score=1)
    a15_3 = Answer(question=q15, text="22m", score=0)

    q16 = Question(module="Advanced", text="Anzahl der Vor-/Rücksprünge?", subtitle="Gebäudestruktur und Kubatur")
    a16_1 = Answer(question=q16, text="Wenig", score=2)
    a16_2 = Answer(question=q16, text="Mittel", score=1)
    a16_3 = Answer(question=q16, text="Viel", score=0)

    q17 = Question(module="Advanced", text="Vorhandene Balkone:", subtitle="Gebäudestruktur und Kubatur")
    a17_1 = Answer(question=q17, text="Keine", score=3)
    a17_2 = Answer(question=q17, text="Wenige", score=2)
    a17_3 = Answer(question=q17, text="Viele entfernbar", score=2)
    a17_4 = Answer(question=q17, text="Viele nicht entfernbar", score=0)

    q18 = Question(module="Advanced", text="Dachüberstände vorhanden?", subtitle="Gebäudestruktur und Kubatur")
    a18_1 = Answer(question=q18, text="Keine", score=2)
    a18_2 = Answer(question=q18, text="Klein <50cm", score=1)
    a18_3 = Answer(question=q18, text="Groß >50cm", score=0)

    q19 = Question(module="Advanced", text="Wie sind die Grenzabstände des Gebäudes auf dem Grundstück?", subtitle="Gebäudestruktur und Kubatur")
    a19_1 = Answer(question=q19, text="Gut, großzügige Abstände", score=2)
    a19_2 = Answer(question=q19, text="Schwierig zu beurteilen", score=1)
    a19_3 = Answer(question=q19, text="Schlecht, enges Grundstück, geringe Abstände", score=0)

    q20 = Question(module="Advanced", text="Um welchen Gebäudetyp handelt es sich?", subtitle="Gebäudetyp und Nutzung")
    a20_1 = Answer(question=q20, text="Wohngebäude", score=2)
    a20_2 = Answer(question=q20, text="Öffentliches Gebäude (Schule/Sporthalle)", score=2)
    a20_3 = Answer(question=q20, text="Gewerbegebäude mit Potenzial zur Umnutzung", score=2)
    a20_4 = Answer(question=q20, text="Mischgebäude ohne Potenzial zur Umnutzung", score=0)

    q21 = Question(module="Advanced", text="Wie viele Wohneinheiten?", subtitle="Gebäudetyp und Nutzung")
    a21_1 = Answer(question=q21, text="<2", score=0)
    a21_2 = Answer(question=q21, text="2–5", score=1)
    a21_3 = Answer(question=q21, text="5", score=2)

    q22 = Question(module="Advanced", text="Baujahr des Gebäudes?", subtitle="Gebäudetyp und Nutzung")
    a22_1 = Answer(question=q22, text="Vor 1950", score=1)
    a22_2 = Answer(question=q22, text="1950–1970", score=4)
    a22_3 = Answer(question=q22, text="1970–1990", score=1)
    a22_4 = Answer(question=q22, text="Nach 1990", score=0)

    q23 = Question(module="Advanced", text="Sind Bestandsunterlagen vorhanden?", subtitle="Gebäudetyp und Nutzung")
    a23_1 = Answer(question=q23, text="Ja", score=2)
    a23_2 = Answer(question=q23, text="Teilweise", score=1)
    a23_3 = Answer(question=q23, text="Nein", score=0)

    q24 = Question(module="Advanced", text="Gibt es Schadstoffbelastungen?", subtitle="Gebäudetyp und Nutzung")
    a24_1 = Answer(question=q24, text="Ja", score=0)
    a24_2 = Answer(question=q24, text="Nein", score=1)
    a24_3 = Answer(question=q24, text="Undefiniert", score=0)

    q25 = Question(module="Advanced", text="Wurden bereits Teilsanierungen durchgeführt?", subtitle="Gebäudetyp und Nutzung")
    a25_1 = Answer(question=q25, text="Nein", score=2)
    a25_2 = Answer(question=q25, text="Ja, gut dokumentiert", score=1)
    a25_3 = Answer(question=q25, text="Ja, undokumentiert", score=0)

    q26 = Question(module="Advanced", text="Tragstruktur in gutem Zustand und geeignet für weitere Lastaufnahme?", subtitle="Statik und Tragfähigkeit")
    a26_1 = Answer(question=q26, text="Klar geeignet", score=2)
    a26_2 = Answer(question=q26, text="Ungeeignet oder unbekannt", score=1)

    q27 = Question(module="Advanced", text="Kellerdecke über Geländeoberkante?", subtitle="Statik und Tragfähigkeit")
    a27_1 = Answer(question=q27, text="Ja (> 50cm)", score=2)
    a27_2 = Answer(question=q27, text="Knapp (<50cm)", score=1)
    a27_3 = Answer(question=q27, text="ebenerdig/tieferliegend", score=0)

    q28 = Question(module="Advanced", text="Gibt es bei ihrem Gebäude eine vorgehängte Fassade?", subtitle="Statik und Tragfähigkeit")
    a28_1 = Answer(question=q28, text="Ja", score=0)
    a28_2 = Answer(question=q28, text="Nein", score=2)
    a28_3 = Answer(question=q28, text="Kann ich nicht beurteilen", score=1)

    q29 = Question(module="Advanced", text="Zustand bestehender Heizungs-/Wasseranlagen/Rohre:", subtitle="Technische Gebäudeausrüstung (TGA)")
    a29_1 = Answer(question=q29, text="Gut nutzbar", score=0)
    a29_2 = Answer(question=q29, text="Sanierungsbedürftig", score=1)
    a29_3 = Answer(question=q29, text="Komplett erneuerungsbedürftig", score=2)

    q30 = Question(module="Advanced", text="Zustand bestehender Elektroinstallationen?", subtitle="Technische Gebäudeausrüstung (TGA)")
    a30_1 = Answer(question=q30, text="Gut nutzbar", score=0)
    a30_2 = Answer(question=q30, text="Sanierungsbedürftig", score=1)
    a30_3 = Answer(question=q30, text="Komplett erneuerungsbedürftig", score=2)

    q31 = Question(module="Advanced", text="Sind zentrale Räume für TGA vorhanden?", subtitle="Technische Gebäudeausrüstung (TGA)")
    a31_1 = Answer(question=q31, text="Ja", score=2)
    a31_2 = Answer(question=q31, text="Teilweise Anpassungen möglich", score=1)
    a31_3 = Answer(question=q31, text="Nicht vorhanden", score=0)

    q32 = Question(module="Advanced", text="Sind zentrale Flure oder Installationsschächte vorhanden, um Leitungen effizient zu verteilen?", subtitle="Technische Gebäudeausrüstung (TGA)")
    a32_1 = Answer(question=q32, text="Ja", score=2)
    a32_2 = Answer(question=q32, text="Teilweise Anpassungen nötig", score=1)
    a32_3 = Answer(question=q32, text="Nein", score=0)

    q33 = Question(module="Advanced", text="Aktuelle Energieeffizienzklasse des Gebäudes ('Worst Performing Building'):", subtitle="Energieeffizienz & Förderfähigkeit")
    a33_1 = Answer(question=q33, text="Sehr schlecht unsaniert vor Bj.1958", score=4)
    a33_2 = Answer(question=q33, text="Mittelmäßig bis schlecht unsaniert Bj.1958–1979", score=2)
    a33_3 = Answer(question=q33, text="Bereits saniert Bj.+1980", score=0)

    q34 = Question(module="Advanced", text="Ziel Energieeffizienzklasse erreichbar?", subtitle="Energieeffizienz & Förderfähigkeit")
    a34_1 = Answer(question=q34, text="Problemlos EH55/EH40 möglich", score=4)
    a34_2 = Answer(question=q34, text="Schwierig EH55 knapp möglich", score=2)
    a34_3 = Answer(question=q34, text="Nicht erreichbar/extrem teuer", score=0)

    q35 = Question(module="Advanced", text="Ist eine Gesamtförderquote von mind. 20-25% möglich?", subtitle="Energieeffizienz & Förderfähigkeit")
    a35_1 = Answer(question=q35, text="Ja", score=4)
    a35_2 = Answer(question=q35, text="Nein", score=0)

    q36 = Question(module="Advanced", text="Gibt es Potential durch zusätzliche Maßnahmen (z.B Pv-Anlagen) höhere Förderquoten zu erreichen?", subtitle="Energieeffizienz & Förderfähigkeit")
    a36_1 = Answer(question=q36, text="Ja problemlos", score=2)
    a36_2 = Answer(question=q36, text="Nur eingeschränkt", score=1)
    a36_3 = Answer(question=q36, text="Nicht möglich", score=0)

    q37 = Question(module="Advanced", text="Zusätzliche Kosten durch Rückbau alter Maßnahmen erwartet?", subtitle="Wirtschaftlichkeit")
    a37_1 = Answer(question=q37, text="Keine Kosten erwartet", score=2)
    a37_2 = Answer(question=q37, text="Zusatzkosten erwartet", score=0)

    q38 = Question(module="Advanced", text="Ist eine Komplettlösung aus einer Hand möglich?", subtitle="Wirtschaftlichkeit")
    a38_1 = Answer(question=q38, text="Ja problemlos möglich", score=3)
    a38_2 = Answer(question=q38, text="Teilweise möglich mit Koordination nötig", score=1)
    a38_3 = Answer(question=q38, text="Nein einzelne Vergabe", score=0)

    q39 = Question(module="Advanced", text="Gibt es Wiederholungsfaktoren im Gebäude oder den Gebäuden?", subtitle="Wirtschaftlichkeit")
    a39_1 = Answer(question=q39, text="Ja die Gebäude sind gleich aufgebaut", score=8)
    a39_2 = Answer(question=q39, text="Teilweise die Stockwerke/Wohneinheiten sind ähnlich", score=4)
    a39_3 = Answer(question=q39, text="Nein es gibt keine oder nur geringe Wiederholungsfaktoren", score=0)

    q40 = Question(module="Advanced", text="Möchten Sie auf Materialien mit geringen Rückbaukosten einsetzen?", subtitle="Nachhaltigkeit und Baustoffqualität")
    a40_1 = Answer(question=q40, text="Ja", score=2)
    a40_2 = Answer(question=q40, text="Teilweise", score=1)
    a40_3 = Answer(question=q40, text="Nein", score=0)

    q41 = Question(module="Advanced", text="Ist Ihnen eine nachhaltige Bauweise wichtig?", subtitle="Nachhaltigkeit und Baustoffqualität")
    a41_1 = Answer(question=q41, text="Ja evtl. auch durch Mehrkosten", score=2)
    a41_2 = Answer(question=q41, text="Teilweise", score=1)
    a41_3 = Answer(question=q41, text="Nein hauptsache billig", score=0)

    q42 = Question(module="Advanced", text="Soll durch die Sanierung eine deutliche Verbesserung der Wohnqualität erreicht werden?", subtitle="Nachhaltigkeit und Baustoffqualität")
    a42_1 = Answer(question=q42, text="Ja", score=2)
    a42_2 = Answer(question=q42, text="Teilweise", score=1)
    a42_3 = Answer(question=q42, text="Nein unwirtschaftlich", score=0)

    q43 = Question(module="Advanced", text="Ist eine schnelle Umsetzung der Sanierung gewünscht (kurze Bauzeit, geringe Mietausfälle)?", subtitle="Ziele des Auftraggebers")
    a43_1 = Answer(question=q43, text="Ja ist möglich", score=2)
    a43_2 = Answer(question=q43, text="Mit Einschränkungen", score=1)
    a43_3 = Answer(question=q43, text="Nein eher nicht Möglich", score=0)

    q44 = Question(module="Advanced", text="Ist es gewünscht das die Mieter während der Sanierung im Objekt wohnen?", subtitle="Ziele des Auftraggebers")
    a44_1 = Answer(question=q44, text="Ja dauerhaft", score=1)
    a44_2 = Answer(question=q44, text="Teilweise soweit wie möglich", score=2)
    a44_3 = Answer(question=q44, text="Nein", score=0)

    q45 = Question(module="Advanced", text="Langfristigen Ziele?", subtitle="Ziele des Auftraggebers")
    a45_1 = Answer(question=q45, text="Langfristige Bestandserhaltung", score=2)
    a45_2 = Answer(question=q45, text="Kurzfristige Renditeorientierung", score=0)
    a45_3 = Answer(question=q45, text="unklar keine klare Strategie", score=1)

    q46 = Question(module="Advanced", text="Ist es gewünscht den Wohnraum zu erweitern?", subtitle="Ziele des Auftraggebers")
    a46_1 = Answer(question=q46, text="Ja durch eine Aufstockung", score=4)
    a46_2 = Answer(question=q46, text="Teilweise z.B. durch Balkone in Wohnraum integrieren", score=2)
    a46_3 = Answer(question=q46, text="Nein", score=0)

    # Füge alle Fragen und Antworten zur Datenbank hinzu
    db.session.add_all([
        # Basic Modul
        q1, q2, q3, q4, q5, q6,
        a3_1, a3_2, a3_3, a3_4, a3_5,
        a4_1, a4_2, a4_3, a4_4,
        a5_1, a5_2, a5_3, a5_4,
        a6_1, a6_2, a6_3,

        # Express Modul
        q7, q8, q9, q10, q11, q12, q13,
        a7_1, a7_2, a7_3, a7_4,
        a8_1, a8_2, a8_3,
        a9_1, a9_2, a9_3,
        a10_1, a10_2,
        a11_1, a11_2, a11_3,
        a12_1, a12_2, a12_3,
        a13_1, a13_2, a13_3,

        # Advanced Modul
        q14, q15, q16, q17, q18, q19, q20, q21, q22, q23, q24, q25, q26, q27, q28, q29, q30, q31, q32, q33, q34, q35, q36, q37, q38, q39, q40, 
        a14_1, a14_2, a14_3,
        a15_1, a15_2, a15_3,
        a16_1, a16_2, a16_3,
        a17_1, a17_2, a17_3, a17_4,
        a18_1, a18_2, a18_3,
        a19_1, a19_2, a19_3,
        a20_1, a20_2, a20_3, a20_4,
        a21_1, a21_2, a21_3,
        a22_1, a22_2, a22_3, a22_4,
        a23_1, a23_2, a23_3,
        a24_1, a24_2, a24_3,
        a25_1, a25_2, a25_3,
        a26_1, a26_2,
        a27_1, a27_2, a27_3,
        a28_1, a28_2, a28_3,
        a29_1, a29_2, a29_3,
        a30_1, a30_2, a30_3,
        a31_1, a31_2, a31_3,
        a32_1, a32_2, a32_3,
        a33_1, a33_2, a33_3,
        a34_1, a34_2, a34_3,
        a35_1, a35_2,
        a36_1, a36_2,a36_3,
        a37_1, a37_2,
        a38_1, a38_2,a38_3,
        a39_1, a39_2,a39_3,
        a40_1, a40_2,a40_3,
        a41_1, a41_2,a41_3,
        a42_1, a42_2,a42_3,
        a43_1, a43_2,a43_3,
        a44_1, a44_2,a44_3,
        a45_1, a45_2,a45_3,
        a46_1, a46_2,a46_3,     


    ])

    db.session.commit()
    print("Datenbank erfolgreich befüllt!")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        populate_database()
    webbrowser.open('http://127.0.0.1:5000')
    app.run(debug=True, use_reloader=False)
