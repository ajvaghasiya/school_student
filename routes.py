import os, sys, shutil
from itsdangerous import URLSafeTimedSerializer
from flask import (Blueprint, Flask, Markup, 
                   current_app, session, request, 
                   url_for, redirect, render_template, send_file, flash, abort)
import uuid, datetime, functools
from dataclasses import asdict
from werkzeug.utils import secure_filename
from passlib.hash import pbkdf2_sha256
from qiskit import (QuantumCircuit, 
                    execute, 
                    Aer)
from qiskit.visualization import plot_histogram
import numpy as np
import unicodedata

sys.path.append("./")
from interface.libs.transpiler.Transpiler import QASM_transpiler, QASM_Pulse_Transpiler
from interface.libs.transpiler.operations import Operations
from interface.libs.quantum_functions.QFT import QFT_circuit
from interface.libs.quantum_functions.oracles import (Simon_oracle,
                                                        BV_oracle,
                                                        DeutschJoszaOracle,
                                                        GroverPhaseOracle,
                                                        GroverInversionOracle)
from interface.libs.quantum_functions.Shor import Shor_Kitaev
from interface.libs.user.Category import CategoryText
import interface.libs.email.email as email
from interface.forms import (RegisterForm, LoginForm, ExperimentForm)
from interface.model import User, Experiment, Result

pages = Blueprint("pages",
                __name__,
                template_folder="templates",
                static_folder="static")

UPLOAD_PATH = os.environ.get("UPLOAD_PATH")

ALLOWED_EXTENSIONS = {'qasm'}


def generate_token(email):
    serializer = URLSafeTimedSerializer(secret_key=current_app.secret_key)
    return serializer.dumps(email, salt=current_app.secret_key)


def confirm_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(current_app.secret_key)
    try:
        email = serializer.loads(
            token,
            salt=current_app.secret_key, 
            max_age=expiration
        )
        return email
    except Exception:
        return False

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


available_processors = [{"name":"Trick",
               "number of qubits": 8,
               "Quantum Volume": 32,
               "CLOPS": 3000,
               "T1 (in sec)": 5,
               "T2 (in sec)": 3,
               "T2* (in sec)": 2.5,
               "Fidelity 0": 0.99,
               "Fidelity 1": 0.98,
               "Fidelity X": 0.96,
               "Fidelity CX": 0.92,

               },
              {"name":"Tick",
               "number of qubits": 4,
               "Quantum Volume": 20,
               "CLOPS": 5000,
               "T1 (in sec)": 12,
               "T2 (in sec)": 10,
               "T2* (in sec)": 7.5,
               "Fidelity 0": 0.999,
               "Fidelity 1": 0.989,
               "Fidelity X": 0.969,
               "Fidelity CX": 0.95
               }, 
               {"name":"Track",
               "number of qubits": 3,
               "Quantum Volume": 15,
               "CLOPS": 1000,
               "T1 (in sec)": 2,
               "T2 (in sec)": 1.25,
               "T2* (in sec)": 1.125,
               "Fidelity 0": 0.90,
               "Fidelity 1": 0.89,
               "Fidelity X": 0.84,
               "Fidelity CX": 0.72
               }]

operations = Operations()

def login_required(route):
    @functools.wraps(route)
    def route_wrapper(*args, **kwargs):
        if session.get("email") is None:
            print("-----=+++++++((((((9))))))-----------",request.url)
            session["next_page"] = request.url

            return redirect(url_for(".login"))
        
        return(route(*args, **kwargs))
    return route_wrapper

def admin_required(route):
    @functools.wraps(route)
    def route_wrapper(*args, **kwargs):
        if session.get("email") is None:
            return redirect(url_for(".login"))
        if not session.get("is_admin"):
            flash("You are no admin", category="danger")
            return redirect(url_for(".login"))
        
        return(route(*args, **kwargs))
    return route_wrapper

## Main SaxonQ-Application Pages
# admin functions
@pages.route("/admin")
@admin_required
def admin_site():
    return render_template("application/admin_site.html",
                           title="SaxonQ -- Admin")

@pages.route("/admin/process_job")
@admin_required
def process_job_admin():
    job_data = current_app.db.open_jobs.find()
    jobs = []
    for job in job_data:
        job["date"] = "{} at {} (CET)".format(job["date"].strftime("%d %B %Y"),
                                          job["date"].strftime("%H:%M:%S "))
        jobs.append(Experiment(**job))
    return render_template("application/admin_open_jobs.html",
                           title="SaxonQ -- Admin OpenJobs",
                           jobs=jobs)

@pages.route("/admin/process_job/evaluating/<string:_jobID>")
@admin_required
def process_job_admin_eval(_jobID: str):
    job_data = current_app.db.open_jobs.find_one({"_id": _jobID})
    if not job_data:
        abort(404)    
    job = asdict(Experiment(**job_data))
    instro = str("\n".join(job["instructions"]))
    if(instro.find("measure") == -1):
        flash("A job needs to have at least one measure instruction", category="danger")
        current_app.db.open_jobs.delete_one({"_id": _jobID})
        return redirect(url_for('.process_job_admin'))
    circuit = QuantumCircuit.from_qasm_str(instro)
    backend = Aer.get_backend('qasm_simulator')
    ex = execute(circuit, backend, shots=1000)
    results = ex.result()
    count = results.get_counts()
    result = Result(_id=uuid.uuid4().hex,
                user_id=job["user_id"],
                open_id=job["_id"],
                processor=job["processor"],
                category=job['category'],
                params=job['params'],
                instructions=job["instructions"],
                result = count,
                date_submit = job["date"], 
                date_finish = datetime.datetime.today())
    current_app.db.processed_jobs.insert_one(asdict(result)) 
    current_app.db.open_jobs.delete_one({"_id": _jobID})  
    job_url = url_for(".processedjob",_jobID=result._id, _external=True)
    html = render_template("notifications/notification_job_processed.html", job_url=job_url)
    subject = "SaxonQ: Your job has been processed"
    user_data = current_app.db.user.find_one({"_id": job["user_id"]})
    if(user_data and not session.get("is_admin")):
        user = User(**user_data)
        email.send_message(user.email, subject, html)
    flash("Job has been processed", "success")
    return redirect(url_for(".process_job_admin"))

@pages.route("/admin/process_job/<string:_jobID>")
@admin_required
def process_openjob(_jobID: str):
    job_data = current_app.db.open_jobs.find_one({"_id": _jobID})
    if not job_data:
        abort(404)    
    job = asdict(Experiment(**job_data))
    job["date"] = "{} at {} (CET)".format(job["date"].strftime("%d %B %Y"),
                                          job["date"].strftime("%H:%M:%S "))
    transpile = QASM_transpiler(job["instructions"])
    transpile.extract_instructions()
    instructions_verbose = transpile.instruction.splitlines()
    job["instructions_verbose"] = instructions_verbose
    jobs_in_line = current_app.db.open_jobs.find({"processor.name": job["processor"]["name"]})
    job["jobs in line"] = -1
    for i in jobs_in_line:
        job["jobs in line"] += 1
    instro = str("\n".join(job["instructions"]))
    if(instro.find("measure") == -1):
        flash("This job does not measure anything", category="danger")
    circuit = QuantumCircuit.from_qasm_str(instro)
    image = circuit.draw(output='mpl')
    f_path = session["file_path"] + '/tmp/' + "figure.svg"
    image.savefig(f_path)
    svg = open(f_path).read()
    category_text = CategoryText(status='open', category=job['category'], params=job['params'])
    return render_template("application/admin_process_open_job.html", 
                           job=job, 
                           figure = Markup(svg),
                           category_text = category_text, 
                           title="SaxonQ -- Admin Process Open Job")


@pages.route("/admin/QST", methods=["GET", "POST"])
@admin_required
def QST():
    if request.method == "POST":
        states = []
        for s in range(session["processor"]["number of qubits"]):
            states.append(request.form.get("q"+str(s)))
        
        return redirect(url_for(".QST"))
    states = ["0", "1", "+", "-"]
    return render_template("application/QST.html", 
                           num_qubit = session["processor"]["number of qubits"],
                            choices = states,
                            title = "SaxonQ -- Quantum State Tomography",
                            figure= None)

@pages.route("/admin/QPT", methods=["GET", "POST"])
@admin_required
def QPT():
    if request.method == "POST":
        states = []
        for s in range(session["processor"]["number of qubits"]):
            states.append(request.form.get("q"+str(s)))
        operation = request.form.get("operation")
        angles = request.form.get("angles")
        return redirect(url_for(".QPT"))
    states = ["0", "1", "+", "-"]
    return render_template("application/QPT.html", 
                           num_qubit=session["processor"]["number of qubits"],
                            choices_states=states,
                            choices_operations=operations.get_operations(),
                            title="SaxonQ -- Quantum Process Tomography")

@pages.route("/admin/choose_processor", methods=["GET", "POST"])
@admin_required
def choose_processor_admin():
    session["QASM"] = False
    if request.method == "POST":
        processor_name = request.form.get("processor")
        for p in available_processors:
            if(p["name"] == processor_name):
                session["processor"] = p
                    
        return redirect(url_for(".choose_maintenance"))
    processors = available_processors
    choices = [processor["name"] for processor in processors]
    return render_template("application/choose_processor.html",
                            processors=available_processors,
                            choices=choices,
                            title="SaxonQ -- Choose Processor")

@pages.route("/admin/choose_maintenance", methods=["GET", "POST"])
@admin_required
def choose_maintenance():
    choices = ["quantum state tomography",
                "quantum process tomography",
                "next maintenance step"]
    if request.method == "POST":
        action = request.form.get("action")
        if(action == "quantum state tomography"):
            return redirect(url_for(".QST"))
        elif(action == "quantum process tomography"):
            return redirect(url_for(".QPT"))
        elif(action == "next maintenance step"):
            return redirect(url_for(".maintenance"))
    return render_template("application/admin_choose_maintenance.html", 
                           choices=choices,
                           title="SaxonQ -- Choose Maintenance")        

# regular user functions
@pages.route("/")
@login_required
def home():
    if not session["email"]:
        return redirect(url_for(".login"))
    user_data = current_app.db.user.find_one({"email": session["email"]})
    if not user_data:
        return redirect(url_for(".register"))
    user = User(**user_data)
    if( not user.is_confirmed):
        return render_template("user_management/inactive.html")
    session["file_path"] = os.getcwd() + '/user/' + str(user._id)
    return render_template(
        "application/home.html",
        title="SaxonQ -- Home",
        user=user
    )

@pages.route("/creator", methods=["GET", "POST"])
@login_required
def job_creator():
    form = ExperimentForm()
    processors = available_processors
    choices = [processor["name"] for processor in processors]
    form.processor.choices = choices

    if request.method == 'POST':
        processor_name = request.form.get("processor")
        for p in processors:
            if(p['name'] == processor_name):
                processor = p
        
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part', category="danger")
            return redirect(url_for(".job_creator"))
        
        file = request.files['file']

        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        if file.filename == '':
            flash('No selected file', category="danger")
            return redirect(url_for(".job_creator"))

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            f_path = session["file_path"] + '/tmp/' + str(filename)
            file.save(f_path)
            with open(f_path) as f:
                instructions = f.read().splitlines()
            session["processor"] = processor
            session["instruction"] = instructions

            return redirect(url_for(".preview"))
        
        else:
            flash("Not an allowed file", category="danger")
    return render_template("application/job_creator.html",
                            choices=choices,
                            form=form,
                            title="SaxonQ -- Job Creator")
    

@pages.route("/preview", methods=["GET", "POST"])
@login_required
def preview():
    if(not session["processor"] or not session["instruction"]):
        return redirect(url_for(".job_creator"))
    
    if request.method == "POST":
        if(str("\n".join(session["instruction"])).find("measure") == -1):
            flash("A job needs to have at least one measure instruction", category="danger")
            return redirect(url_for(".job_creator"))
        transpile = QASM_Pulse_Transpiler(session["instruction"])
        transpile.extract_instructions()
        instructions_pulse = transpile.instruction.splitlines()
    
        user_data = current_app.db.user.find_one({"email": session["email"]})
        user = User(**user_data)
        job = Experiment(_id=uuid.uuid4().hex,
                        user_id=user._id,
                        processor=session["processor"],
                        category="manual",
                        params={'none' : None},
                        instructions=session["instruction"],
                        instructions_pulse=instructions_pulse,
                        date = datetime.datetime.today())
        current_app.db.open_jobs.insert_one(asdict(job))
        
        flash("Job has been submitted", "success")
        job_url = url_for(".openjob",_jobID=job._id, _external=True)
        html = render_template("notifications/notification_job_submitted.html", job_url=job_url)
        subject = "SaxonQ: You submitted a job"
        if not session.get("is_admin"):
            email.send_message(user.email, subject, html)
        return redirect(url_for(".job_creator"))
    
    transpile = QASM_transpiler(session["instruction"])
    transpile.extract_instructions()
    instructions_verbose = transpile.instruction.splitlines()
    instro = str("\n".join(session["instruction"]))
    session["QASM"] = instro    
    circuit = QuantumCircuit.from_qasm_str(instro)
    image = circuit.draw(output='mpl')
    f_path = session["file_path"] + '/tmp/' + "figure.svg"
    image.savefig(f_path)
    svg = open(f_path).read()
    return render_template("application/preview.html",
                           processor=session["processor"],
                           instructions=session["instruction"],
                           instructions_verbose=instructions_verbose,
                           figure = Markup(svg),
                           title="SaxonQ -- Job Preview")

@pages.route("/download")
@login_required
def download_QASM():
    if(session["QASM"]):
        f_path = session["file_path"]+'/tmp/OpenQASM_file_'+str(datetime.datetime.today())+'.qasm'
        with open(f_path, "w") as f:
            f.write(session["QASM"])
        return send_file(f_path, as_attachment=True)
        
    flash("Please create an OpenQASM file first", category="danger")
    return redirect(url_for(".preview"))

@pages.route("/circuit_creator", methods=["GET", "POST"])
@login_required
def circuit_creator():
    for p in available_processors:
        if(p["name"] == session["processor"]["name"]):
            processor = p

    session["num_qbits"] = processor["number of qubits"]
    session["num_cbits"] = session['num_qbits']
    qubits  = ["q["+str(i)+"]" for i in range(session["num_qbits"])]
    if request.method == "POST":
        if not session['QASM']:
            session['QASM'] = "OPENQASM 2.0;\ninclude "+ '"'+"qelib1.inc"+'"' + ";\n"
            session['QASM'] += "qreg q["+str(session["num_qbits"])+'];\n'
            session["QASM"] += "creg c["+str(session["num_qbits"])+'];\n'
        for p in available_processors:
            if(p["name"] == session["processor"]["name"]):
                processor = p 

        o = request.form.get("operation")
        t = request.form.get("target")
        c = request.form.get("control")
        a = request.form.get("angles").split(',')
        instruction = operations.get_QASM_instruction(operation=o,
                                                      target=t,
                                                      control=c,
                                                      rotation=a)
        if(instruction.find("Error") == -1):
            session["QASM"] += instruction + '\n'
            circuit = QuantumCircuit.from_qasm_str(session["QASM"])
            image = circuit.draw(output='mpl')
            f_path = session["file_path"] + '/tmp/' + "figure.svg"
            image.savefig(f_path)
            svg = open(f_path).read()
        else:
            svg = False
            flash(instruction, category="danger")        
        return render_template("application/circuit_creator.html", 
                                figure = Markup(svg),
                                choices_operations=operations.get_operations(),
                                choices_target=qubits,
                                choices_control=qubits,
                                lines=session["QASM"].splitlines(),
                                title="SaxonQ -- Circuit Creator")
    if(session["QASM"]):
        circuit = QuantumCircuit.from_qasm_str(session["QASM"])
        image = circuit.draw(output='mpl')
        f_path = session["file_path"] + '/tmp/' + "figure.svg"
        image.savefig(f_path)
        svg = open(f_path).read()
        return render_template("application/circuit_creator.html", 
                            choices_operations=operations.get_operations(),
                            choices_target=qubits,
                            choices_control=qubits,
                            figure = Markup(svg),
                            lines=session["QASM"].splitlines(),
                            title="SaxonQ -- Circuit Creator")
    return render_template("application/circuit_creator.html", 
                    choices_operations=operations.get_operations(),
                    choices_target=qubits,
                    choices_control=qubits,
                    title="SaxonQ -- Circuit Creator")


@pages.route("/circuit_creator/clear_circuit")
@login_required
def clear_circuit():
    session["QASM"] = False
    return redirect(url_for('.circuit_creator'))

@pages.route("/circuit_creator/choose_processor", methods=["GET", "POST"])
@login_required
def choose_processor():
    session["QASM"] = False
    if request.method == "POST":
        processor_name = request.form.get("processor")
        for p in available_processors:
            if(p["name"] == processor_name):
                session["processor"] = p
                    
        return redirect(url_for(".circuit_creator"))
    processors = available_processors
    choices = [processor["name"] for processor in processors]
    return render_template("application/choose_processor.html",
                            processors=available_processors,
                            choices=choices,
                            title="SaxonQ -- Choose Processor")

@pages.route("/circuit_creator/delete_line/<string:num>")
@login_required
def delete_line(num: int):
    if(int(num) < 5):
        flash("This line can not be deleted", category="danger")
        return redirect(url_for(".circuit_creator"))    
    code = ''
    old_code = session["QASM"].splitlines()
    for i, line in enumerate(old_code):
        if(i+1 != int(num)):
            code += line + '\n'
    session["QASM"] = code
    return redirect(url_for(".circuit_creator"))

@pages.route("/circuit_creator/make_OpenQASM_file")
@login_required
def make_QASM_file():
    if(session["QASM"]):
        if(session["QASM"].find("measure") == -1):
            flash("A job needs to have at least one measure instruction", category="danger")
            return redirect(url_for(".circuit_creator"))
        session["instruction"] = session["QASM"].splitlines()
        return redirect(url_for(".preview"))
    flash("Please create a quantum circuit", category="danger")
    return redirect(url_for(".circuit_creator"))

@pages.route("/processors")
@login_required
def processors():
    processors = available_processors
    for i, p in enumerate(processors):
        jobs_in_line = current_app.db.open_jobs.find({"processor.name": p["name"]})
        processors[i]["jobs_in_line"] = int(10*np.random.random()) + 5
        for job in jobs_in_line:
            processors[i]["jobs_in_line"] += 1 
    return render_template("application/processors.html", 
                           processors=processors,
                           title="SaxonQ -- Processors")

@pages.route("/QASM_HELP")
@login_required
def QASM_instruction():
    return render_template("application/QASM_help.html")

@pages.route("/inspector")
@login_required
def job_inspector():
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    if(user.is_admin):
        # open jobs
        ojobs = current_app.db.open_jobs.find()
        open_jobs = []
        for job in ojobs:
            experiment = Experiment(**job)
            open_jobs.append(experiment)
        
        # processed jobs
        pjobs = current_app.db.processed_jobs.find()
        processed_jobs = []
        for job in pjobs:
            result = Result(**job)
            processed_jobs.append(result)
        return render_template("application/job_inspector.html", 
                           open_jobs=open_jobs,
                           processed_jobs=processed_jobs,
                           title="SaxonQ -- Job Inspector")
    
    # open jobs
    ojobs = current_app.db.open_jobs.find({"user_id": user._id})
    open_jobs = []
    for job in ojobs:
        experiment = Experiment(**job)
        open_jobs.append(experiment)
    
    # processed jobs
    pjobs = current_app.db.processed_jobs.find({"user_id": user._id})
    processed_jobs = []
    for job in pjobs:
        result = Result(**job)
        processed_jobs.append(result)

    return render_template("application/job_inspector.html", 
                           open_jobs=open_jobs,
                           processed_jobs=processed_jobs,
                           title="SaxonQ -- Job Inspector")


@pages.route("/job_inspector/open_job/<string:_jobID>")
@login_required
def openjob(_jobID: str):
    job_data = current_app.db.open_jobs.find_one({"_id": _jobID})
    if not job_data:
        job_data = current_app.db.processed_jobs.find_one({"open_id": _jobID})
        if not job_data:
            abort(404)
        else:
            flash("Your job has already been processed", category="success")
            job = asdict(Result(**job_data))
            return redirect(url_for(".processedjob",_jobID=job["_id"]))
    job = asdict(Experiment(**job_data))
    job["date"] = "{} at {} (CET)".format(job["date"].strftime("%d %B %Y"),
                                          job["date"].strftime("%H:%M:%S "))
    transpile = QASM_transpiler(job["instructions"])
    transpile.extract_instructions()
    instructions_verbose = transpile.instruction.splitlines()
    job["instructions_verbose"] = instructions_verbose
    
    jobs_in_line = current_app.db.open_jobs.find({"processor.name": job["processor"]["name"]})
    job["jobs in line"] = int(10*np.random.random()) + 5
    for i in jobs_in_line:
        job["jobs in line"] += 1
    instro = str("\n".join(job["instructions"]))
    circuit = QuantumCircuit.from_qasm_str(instro)
    image = circuit.draw(output='mpl')
    f_path = session["file_path"] + '/tmp/' + "figure.svg"
    image.savefig(f_path)
    svg = open(f_path).read()
    category_text = CategoryText(status='open', category=job['category'], params=job['params'])
    return render_template("application/open_job.html", 
                           job = job, 
                           figure = Markup(svg),
                           category_text = category_text, 
                           title="SaxonQ -- Open Job")

@pages.route("/job_inspector/processed_job/<string:_jobID>")
@login_required
def processedjob(_jobID: str):
    job_data = current_app.db.processed_jobs.find_one({"_id": _jobID})
    if not job_data:
        abort(404)    
    job = asdict(Result(**job_data))
    job["date_submit"] = "{} at {} (CET)".format(job["date_submit"].strftime("%d %B %Y"),
                                          job["date_submit"].strftime("%H:%M:%S "))
    job["date_finish"] = "{} at {} (CET)".format(job["date_finish"].strftime("%d %B %Y"),
                                          job["date_finish"].strftime("%H:%M:%S "))
    transpile = QASM_transpiler(job["instructions"])
    transpile.extract_instructions()
    instructions_verbose = transpile.instruction.splitlines()
    job["instructions_verbose"] = instructions_verbose
    instro = str("\n".join(job["instructions"]))
    image = plot_histogram(job["result"])
    f_path = session["file_path"] + '/tmp/' + "histogram.svg"
    image.savefig(f_path, bbox_inches="tight")
    svg_histogram = open(f_path).read()
    circuit = QuantumCircuit.from_qasm_str(instro)
    image = circuit.draw(output='mpl')
    f_path = session["file_path"] + '/tmp/' + "circuit.svg"
    image.savefig(f_path)
    svg_circuit = open(f_path).read()
    category_text = CategoryText(status='processed', 
                                 category=job['category'], 
                                 results=job['result'] , 
                                 params=job['params'])
    return render_template("application/processed_job.html", 
                           job=job, 
                           svg_circuit = Markup(svg_circuit),
                           svg_histogram = Markup(svg_histogram),
                           category_text = category_text,
                           title="SaxonQ -- Processed Job")


## User management
@pages.route("/create_admin", methods=["POST", "GET"])
def create_admin():
    if session.get("email"):
        return redirect(url_for(".home"))
    form = RegisterForm()
    if form.validate_on_submit():
        user_data = current_app.db.user.find_one({"email": "admin@saxonq.com"})
        if user_data:
            flash("There is already an admin registered", category="danger")
            return redirect(url_for(".login"))
        user = User(_id= uuid.uuid4().hex,
                    email= os.environ.get("ADMIN-MAIL"),
                    password=pbkdf2_sha256.hash(form.password.data),
                    is_admin = True,
                    is_confirmed = True)
        
        upload_folder = str(os.getcwd()) + '/' + str(UPLOAD_PATH) + '/' + str(user._id)
        os.makedirs(upload_folder)
        current_app.db.user.insert_one(asdict(user))
        flash("Admin registered successfully", "success")
        
        return redirect(url_for(".home"))

    return render_template("user_management/register.html", 
                           title="SaxonQ -- Register", 
                           form=form)

@pages.route("/register", methods=["POST", "GET"])
def register():
    if session.get("email"):
        return redirect(url_for(".home"))
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(_id= uuid.uuid4().hex,
                    email=form.email.data,
                    password=pbkdf2_sha256.hash(form.password.data))
        if current_app.db.user.find_one({"email": user.email}):
            flash("You already have an account", category="success")
            return redirect(url_for(".login"))
        upload_folder = str(os.getcwd()) + '/' + str(UPLOAD_PATH) + str(user._id)
        os.makedirs(upload_folder)
        os.makedirs(upload_folder+'/tmp')
        current_app.db.user.insert_one(asdict(user))
        token = generate_token(user.email)
        # Session line added by Akshay - 20.07.2023
        session["email"] = user.email
        confirm_url = url_for(".confirm_email", token=token, _external=True)
        html = render_template("user_management/confirm_email.html", confirm_url=confirm_url)
        subject = "Please confirm your email"
        email.send_message(user.email, subject, html)
        flash("A confirmation email has been sent to you.", "success")
        return redirect(url_for("pages.inactive"))

    return render_template("user_management/register.html", 
                           title="SaxonQ -- Register", 
                           form=form)

@pages.route("/confirm/<token>")
@login_required
def confirm_email(token):
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    if user.is_confirmed:
        flash("Account already confirmed.", "success")
        return redirect(url_for(".login"))
    email = confirm_token(token)
    
    if user.email == email:
        current_app.db.user.update_one({"_id": user._id}, {"$set": {"is_confirmed": True}})
        flash("You have confirmed your account. Thanks!", "success")
    else:
        flash("The confirmation link is invalid or has expired.", "danger")
    return redirect(url_for(".login"))

@pages.route("/redirect_to_varify")
@login_required
def verify_account():
    user_data = current_app.db.user.find_one({"email": session["email"]})
    if not user_data:
        flash("Login credentials not correct", category="danger")
        return redirect(url_for(".login"))
    user = User(**user_data)
    if user.is_confirmed:
        # return redirect(url_for(".home"))
        next_page = session.get('next_page')
        print("))))))))00000000000000000000000000000000", next_page)
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('.home')
        session.pop('next_page', None)
        print("$$$$$$$$$$$$$$$$-$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
        return redirect(next_page)
    else:
        flash("Verify your account by clicking on the link in the email we sent you", category="danger")
        return render_template("user_management/inactive.html")

@pages.route("/resend")
@login_required
def resend_confirmation():
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    if user.is_confirmed:
        flash("Your account has already been confirmed.", "success")
        return redirect(url_for("pages.home"))
    token = generate_token(user.email)
    confirm_url = url_for("pages.confirm_email", token=token, _external=True)
    html = render_template("user_management/confirm_email.html", confirm_url=confirm_url)
    subject = "Please confirm your email"
    if not session.get("is_admin"):
        email.send_message(user.email, subject, html)
    flash("A new confirmation email has been sent.", "success")
    return redirect(url_for(".inactive"))

@pages.route("/inactive")
@login_required
def inactive():
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    if user.is_confirmed:
        return redirect(url_for(".home"))
    return render_template("user_management/inactive.html")

@pages.route("/login", methods=["GET", "POST"])
def login():
    if session.get("email"):
        return redirect(url_for(".verify_account"))

    form = LoginForm()

    if form.validate_on_submit():
        user_data = current_app.db.user.find_one({"email": form.email.data})
        if not user_data:
            flash("Login credentials not correct", category="danger")
            return redirect(url_for(".login"))
        user = User(**user_data)

        if user and pbkdf2_sha256.verify(form.password.data, user.password):
            session["email"] = user.email
            session["file_path"] = os.getcwd() + '/' + str(UPLOAD_PATH) + str(user._id)
            session["is_admin"] = user.is_admin
            next_page = session.get("next_page")
            print("---+++++++++--- nect page value-------=======", next_page)
            if not os.path.exists(session["file_path"] + '/tmp'):
                os.makedirs(session["file_path"] + '/tmp')

            return redirect(url_for(".verify_account"))

        flash("Login credentials not correct", category="danger")

    return render_template("user_management/login.html", title="SaxonQ -- Login", form=form)


@pages.route("/logout")
@login_required
def logout():
    tmp_path = session["file_path"]+'/tmp'
    if os.path.exists(tmp_path):
        shutil.rmtree(tmp_path)
    session.clear()
    return redirect(url_for(".login"))

@pages.route("/author")
def author():
    return render_template("author.html")

@pages.route("/contact")
def contact_author():
    return render_template("contact_author.html")

## Quantum Computing moduls
@login_required
@pages.route("/QuantumComputingLearning")
def QClearning():
    return render_template("QClearning/QClearningtableofcontent.html", title="SaxonQ -- Tutorial")

@login_required
@pages.route("/QuantumComputingLearning/Superposition")
def Superposition():
    return render_template("QClearning/Superposition.html", title="SaxonQ -- Superposition")

@login_required
@pages.route("/QuantumComputingLearning/Superposition_creation")
def Superposition_creation():
    ## randomly select an available processor
    session['processor'] = available_processors[int(np.random.random()*len(available_processors))]
    n = session['processor']['number of qubits']
    qc = QuantumCircuit(n,n)
    qc.h(range(n))
    qc.measure(range(n), range(n))
    
    ## submit job
    session["QASM"] = qc.qasm()
    session["instruction"] = session["QASM"].splitlines()
    transpile = QASM_Pulse_Transpiler(session["instruction"])
    transpile.extract_instructions()
    instructions_pulse = transpile.instruction.splitlines()
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    job = Experiment(_id=uuid.uuid4().hex,
                    user_id=user._id,
                    category="Superposition",
                    params={"none" : None},
                    processor=session["processor"],
                    instructions=session["instruction"],
                    instructions_pulse=instructions_pulse,
                    date = datetime.datetime.today())
    current_app.db.open_jobs.insert_one(asdict(job))
    flash(f"Job has been submitted \n You created a superposition of all possible states", "success")
    job_url = url_for(".openjob",_jobID=job._id, _external=True)
    html = render_template("notifications/notification_superposition_job_submitted.html", job_url=job_url)
    subject = "SaxonQ: You submitted a job"
    if not session.get("is_admin"):
        email.send_message(user.email, subject, html)
    return redirect(url_for(".QClearning"))

@login_required
@pages.route("/QuantumComputingLearning/SWAP")
def SWAP():
    return render_template("QClearning/SWAP.html", title="SaxonQ -- SWAP")

@login_required
@pages.route("/QuantumComputingLearning/SWAP_creation")
def SWAP_creation():
    ## randomly select an available processor
    session['processor'] = available_processors[int(np.random.random()*len(available_processors))]
    
    ## select an available processor with enough qubits
    for p in available_processors:
        if(p["number of qubits"] > 1):
            session['processor'] = p
            break
    n = session['processor']['number of qubits']
    if n < 2:
        flash("Our system has no available processor with enough qubits at the moment. Please try again later", "danger")
        return redirect(url_for(".QClearning"))
    
    qc = QuantumCircuit(n,n)
    
    ## create a one in the first qubit
    qc.x(0)
    ## swap it into the last qubit
    for i in range(n-1):
        qc.cx(i,i+1)
        qc.cx(i+1,i)
        qc.cx(i,i+1)
    qc.measure(range(n), range(n))
    
    ## submit job
    session["QASM"] = qc.qasm()
    session["instruction"] = session["QASM"].splitlines()
    transpile = QASM_Pulse_Transpiler(session["instruction"])
    transpile.extract_instructions()
    instructions_pulse = transpile.instruction.splitlines()
    
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    job = Experiment(_id=uuid.uuid4().hex,
                    user_id=user._id,
                    category="SWAP",
                    params={"none" : None},
                    processor=session["processor"],
                    instructions=session["instruction"],
                    instructions_pulse=instructions_pulse,
                    date = datetime.datetime.today())
    current_app.db.open_jobs.insert_one(asdict(job))
    flash(f"Job has been submitted \n You transferred the one from the first qubit into the last qubit", "success")
    job_url = url_for(".openjob",_jobID=job._id, _external=True)
    html = render_template("notifications/notification_SWAP_job_submitted.html", job_url=job_url)
    subject = "SaxonQ: You submitted a job"
    if not session.get("is_admin"):
        email.send_message(user.email, subject, html)
    return redirect(url_for(".QClearning"))

@login_required
@pages.route("/QuantumComputingLearning/Quantum_Teleportation")
def QuantumTeleport():
    return render_template("QClearning/QuantumTeleportation.html", title="SaxonQ -- Quantum Teleportation")

@login_required
@pages.route("/QuantumComputingLearning/Teleportation_creation")
def Teleportation_creation():
    ## randomly select an available processor
    session['processor'] = available_processors[int(np.random.random()*len(available_processors))]

    ## select an available processor with enough qubits
    for p in available_processors:
        if(p["number of qubits"] > 2):
            session['processor'] = p
            break
    
    n = session['processor']['number of qubits']
    if n < 3:
        flash("Our system has no available processor with enough qubits at the moment. Please try again later", "danger")
        return redirect(url_for(".QClearning"))
    
    ## build Quantum Teleportation state circuit
    qc = QuantumCircuit(n,1)

    # an arbitrary X-Rotation
    r_angle = 2*np.pi*np.random.random()
    qc.rx(r_angle,0)

    # creation of Bell state 00
    qc.h(1)
    qc.cx(1,2)

    # the teleportation protocol
    qc.cx(0,1)
    qc.h(0)
    qc.cx(1,2)
    qc.cz(0,2)
    qc.measure(2, 0)

    ## submit job
    session["QASM"] = qc.qasm()
    session["instruction"] = session["QASM"].splitlines()
    transpile = QASM_Pulse_Transpiler(session["instruction"])
    transpile.extract_instructions()
    instructions_pulse = transpile.instruction.splitlines()
    
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    job = Experiment(_id=uuid.uuid4().hex,
                    user_id=user._id,
                    processor=session["processor"],
                    category="Quantum Teleportation",
                    params={"angle" : r_angle},
                    instructions=session["instruction"],
                    instructions_pulse=instructions_pulse,
                    date = datetime.datetime.today())
    current_app.db.open_jobs.insert_one(asdict(job))
    r_angle_string = f"{(r_angle/(np.pi)):.3f}" + unicodedata.lookup("GREEK SMALL LETTER PI")
    
    flash(f"Job has been submitted \n You created the state R_x({r_angle_string})|0> and teleported it", "success")
    job_url = url_for(".openjob",_jobID=job._id, _external=True)
    html = render_template("notifications/notification_Teleport_job_submitted.html", angle=r_angle, job_url=job_url)
    subject = "SaxonQ: You submitted a job"
    if not session.get("is_admin"):
        email.send_message(user.email, subject, html)
    return redirect(url_for(".QClearning"))

@login_required
@pages.route("/QuantumComputingLearning/Bell_States")
def BellStates():
    return render_template("QClearning/BellStates.html", title="SaxonQ -- Bell States")

@login_required
@pages.route("/QuantumComputingLearning/Bell_States_creation")
def BellStates_creation():
    ## randomly select an available processor
    session['processor'] = available_processors[int(np.random.random()*len(available_processors))]

    ## select an available processor with enough qubits
    for p in available_processors:
        if(p["number of qubits"] > 1):
            session['processor'] = p
            break
    
    n = session['processor']['number of qubits']
    if n < 2:
        flash("Our system has no available processor with enough qubits at the moment. Please try again later", "danger")
        return redirect(url_for(".QClearning"))
    BS_code = []
    for i in range(2):
        r = np.random.random()
        if r<0.5:
            BS_code.append(0)
        else:
            BS_code.append(1)
    ## build Bell state circuit
    qc = QuantumCircuit(n,2)
    for i in range(2):
        if(BS_code[i] == 1):
            qc.x(i)
    qc.h(0)
    qc.cx(0,1)
    qc.measure(range(2), range(2))

    ## submit job
    session["QASM"] = qc.qasm()
    session["instruction"] = session["QASM"].splitlines()
    transpile = QASM_Pulse_Transpiler(session["instruction"])
    transpile.extract_instructions()
    instructions_pulse = transpile.instruction.splitlines()
    
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    BS_string = ""
    for s in BS_code[::-1]:
        BS_string += str(s)
    BS_string += ''
    job = Experiment(_id=uuid.uuid4().hex,
                    user_id=user._id,
                    processor=session["processor"],
                    category="BellStates",
                    params={"BellState" : BS_string},
                    instructions=session["instruction"],
                    instructions_pulse=instructions_pulse,
                    date = datetime.datetime.today())
    current_app.db.open_jobs.insert_one(asdict(job))
    
    flash(f"Job has been submitted \n You created the Bell state {BS_string}", "success")
    job_url = url_for(".openjob",_jobID=job._id, _external=True)
    html = render_template("notifications/notification_BellStates_job_submitted.html", BS=BS_string, job_url=job_url)
    subject = "SaxonQ: You submitted a job"
    if not session.get("is_admin"):
        email.send_message(user.email, subject, html)
    return redirect(url_for(".QClearning"))

@login_required
@pages.route("/QuantumComputingLearning/GHZ_States")
def GHZStates():
    return render_template("QClearning/GHZStates.html", title="SaxonQ -- GHZ States")

@login_required
@pages.route("/QuantumComputingLearning/GHZ_States_creation")
def GHZStates_creation():
    ## randomly select an available processor
    session['processor'] = available_processors[int(np.random.random()*len(available_processors))]

    ## select an available processor with enough qubits
    for p in available_processors:
        if(p["number of qubits"] > 2):
            session['processor'] = p
            break
    n = session['processor']['number of qubits']
    if n < 3:
        flash("Our system has no available processor with enough qubits at the moment. Please try again later", "danger")
        return redirect(url_for(".QClearning"))
    GHZ_code = []
    for i in range(n):
        r = np.random.random()
        if r<0.5:
            GHZ_code.append(0)
        else:
            GHZ_code.append(1)

    ## build GHZ state circuit
    qc = QuantumCircuit(n,n)
    for i in range(n):
        if(GHZ_code[i] == 1):
            qc.x(i)
    qc.h(0)
    for i in range(n-1):
        qc.cx(i,i+1)
    qc.measure(range(n), range(n))

    ## submit job
    session["QASM"] = qc.qasm()
    session["instruction"] = session["QASM"].splitlines()
    transpile = QASM_Pulse_Transpiler(session["instruction"])
    transpile.extract_instructions()
    instructions_pulse = transpile.instruction.splitlines()
    
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    GHZ_string = ""
    for s in GHZ_code[::-1]:
        GHZ_string += str(s)
    GHZ_string += ''
    job = Experiment(_id=uuid.uuid4().hex,
                    user_id=user._id,
                    processor=session["processor"],
                    category="GHZ",
                    params={"GHZState" : GHZ_string},
                    instructions=session["instruction"],
                    instructions_pulse=instructions_pulse,
                    date = datetime.datetime.today())
    current_app.db.open_jobs.insert_one(asdict(job))
    
    GHZ_string = ""
    for s in GHZ_code[::-1]:
        GHZ_string += str(s)
    GHZ_string += ''
    flash(f"Job has been submitted \n You created the {GHZ_string} GHZ state", "success")
    job_url = url_for(".openjob",_jobID=job._id, _external=True)
    html = render_template("notifications/notification_GHZ_job_submitted.html", GHZ=GHZ_string, job_url=job_url)
    subject = "SaxonQ: You submitted a job"
    if not session.get("is_admin"):
        email.send_message(user.email, subject, html)
    return redirect(url_for(".QClearning"))

@login_required
@pages.route("/QuantumComputingLearning/Deutsch_algorithm")
def Deutsch():
    return render_template("QClearning/Deutsch.html", title="SaxonQ -- Deutsch")

login_required
@pages.route("/QuantumComputingLearning/Deutsch_algorithm_create")
def Deutsch_creation():
    ## randomly select an available processor
    session['processor'] = available_processors[int(np.random.random()*len(available_processors))]

    ## select an available processor with enough qubits
    for p in available_processors:
        if(p["number of qubits"] > 1):
            session['processor'] = p
            break
    
    n = session['processor']['number of qubits']
    if n < 2:
        flash("Our system has no available processor with enough qubits at the moment. Please try again later", "danger")
        return redirect(url_for(".QClearning"))
    
    ## Choose a type of oracle at random. 
    # With probability one-half it is constant
    # and with the same probability it is balanced
    oracleType, oracleValue = np.random.randint(2), np.random.randint(2)
    
    qc = QuantumCircuit(n,1)
    qc.x(1)
    for i in range(2):
        qc.h(i)
    # apply the oracle
    oracleType, oracleValue = np.random.randint(2), np.random.randint(2)
    if oracleType == 0:
        s = f"constant with value = {oracleValue}"
    else:
        s = f"balanced "
    qc = QuantumCircuit.compose(qc, DeutschJoszaOracle(2, oracleType=oracleType, oracleValue=oracleValue))
    
    # determine the indicator qubit
    qc.h(0)
    qc.measure(0,0)

    ## submit job
    session["QASM"] = qc.qasm()
    session["instruction"] = session["QASM"].splitlines()
    transpile = QASM_Pulse_Transpiler(session["instruction"])
    transpile.extract_instructions()
    instructions_pulse = transpile.instruction.splitlines()
    
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    job = Experiment(_id=uuid.uuid4().hex,
                    user_id=user._id,
                    processor=session["processor"],
                    category="DeutschJosza",
                    params={"oracle" : s},
                    instructions=session["instruction"],
                    instructions_pulse=instructions_pulse,
                    date = datetime.datetime.today())
    current_app.db.open_jobs.insert_one(asdict(job))
    
    flash(f"Job has been submitted \n Your oracle is {s}", "success")
    job_url = url_for(".openjob",_jobID=job._id, _external=True)
    html = render_template("notifications/notification_Deutsch_job_submitted.html", oracle = s, job_url=job_url)
    subject = "SaxonQ: You submitted a job"
    if not session.get("is_admin"):
        email.send_message(user.email, subject, html)
    return redirect(url_for(".QClearning"))

@login_required
@pages.route("/QuantumComputingLearning/Deutsch_Josza_algorithm")
def DeutschJosza():
    return render_template("QClearning/DeutschJosza.html", title="SaxonQ -- Deutsch-Josza")

@login_required
@pages.route("/QuantumComputingLearning/Deutsch_Josza_algorithm_create")
def DeutschJosza_creation():
    ## randomly select an available processor
    session['processor'] = available_processors[int(np.random.random()*len(available_processors))]

    ## select an available processor with enough qubits
    for p in available_processors:
        if(p["number of qubits"] > 2):
            session['processor'] = p
            break
    
    n = session['processor']['number of qubits']
    if n < 3:
        flash("Our system has no available processor with enough qubits at the moment. Please try again later", "danger")
        return redirect(url_for(".QClearning"))
    
    ## Choose a type of oracle at random. 
    # With probability one-half it is constant
    # and with the same probability it is balanced
    qc = QuantumCircuit(n,n-1)
    qc.x(n-1)
    for i in range(n):
        qc.h(i)
    
    # apply the oracle
    oracleType, oracleValue = np.random.randint(2), np.random.randint(2)
    qc = QuantumCircuit.compose(qc, DeutschJoszaOracle(n, oracleType=oracleType, oracleValue=oracleValue))
    if oracleType == 0:
        s = f"constant with value = {oracleValue}"
    else:
        s = f"balanced"
    
    # determine the indicator qubit
    qc.h(range(n-1))
    qc.measure(range(n-1),range(n-1))

    ## submit job
    session["QASM"] = qc.qasm()
    session["instruction"] = session["QASM"].splitlines()
    transpile = QASM_Pulse_Transpiler(session["instruction"])
    transpile.extract_instructions()
    instructions_pulse = transpile.instruction.splitlines()
    
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    job = Experiment(_id=uuid.uuid4().hex,
                    user_id=user._id,
                    processor=session["processor"],
                    category="DeutschJosza",
                    params={"oracle" : s},
                    instructions=session["instruction"],
                    instructions_pulse=instructions_pulse,
                    date = datetime.datetime.today())
    current_app.db.open_jobs.insert_one(asdict(job))
    
    flash(f"Job has been submitted \n Your oracle is {s}", "success")
    job_url = url_for(".openjob",_jobID=job._id, _external=True)
    html = render_template("notifications/notification_Deutsch_Josza_job_submitted.html", oracle = s, job_url=job_url)
    subject = "SaxonQ: You submitted a job"
    if not session.get("is_admin"):
        email.send_message(user.email, subject, html)
    return redirect(url_for(".QClearning"))

@login_required
@pages.route("/QuantumComputingLearning/Quantum_Fourier_Transformation")
def QFT():
    return render_template("QClearning/QFT.html", title="SaxonQ -- Quantum Fourier Transformation")

@login_required
@pages.route("/QuantumComputingLearning/Quantum_Fourier_Tranformation_create")
def QFT_creation():
    ## randomly select an available processor
    session['processor'] = available_processors[int(np.random.random()*len(available_processors))]
    n = session['processor']['number of qubits']

    ## select an available processor with enough qubits
    for p in available_processors:
        if(p["number of qubits"] > 2):
            session['processor'] = p
            break
    n = session['processor']['number of qubits']
    if n < 2:
        flash("Our system has no available processor with enough qubits at the moment. Please try again later", "danger")
        return redirect(url_for(".QClearning"))
    
    ## prepare a state with period k
    k = str(format(np.random.random_integers(n),"b").zfill(n))
    qc = QuantumCircuit(n,n)
    qc.h(range(n))
    angles = np.zeros(n)
    for i in range(n):
        j = n - i
        for l in reversed(range(j)):
            angles[i] += -2*np.pi*int(k[l])/2**(j-l)
    for i in range(n):
        qc.rz(angles[i],i)
    qc = QuantumCircuit.compose(qc, QFT_circuit(n))
    qc.measure(range(n), range(n))
    
    ## submit job
    session["QASM"] = qc.qasm()
    session["instruction"] = session["QASM"].splitlines()
    transpile = QASM_Pulse_Transpiler(session["instruction"])
    transpile.extract_instructions()
    instructions_pulse = transpile.instruction.splitlines()
    
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    job = Experiment(_id=uuid.uuid4().hex,
                    user_id=user._id,
                    processor=session["processor"],
                    category="QFT",
                    params={"period" : str(k)},
                    instructions=session["instruction"],
                    instructions_pulse=instructions_pulse,
                    date = datetime.datetime.today())
    current_app.db.open_jobs.insert_one(asdict(job))
    
    flash(f"Job has been submitted \n Your state has a period of {k}", "success")
    job_url = url_for(".openjob",_jobID=job._id, _external=True)
    html = render_template("notifications/notification_QFT_job_submitted.html", period = k, job_url=job_url)
    subject = "SaxonQ: You submitted a job"
    if not session.get("is_admin"):
        email.send_message(user.email, subject, html)
    return redirect(url_for(".QClearning"))

@login_required
@pages.route("/QuantumComputingLearning/Bernstein_Vazirani_algorithm")
def BV():
    return render_template("QClearning/BV.html", title="SaxonQ -- Bernstein-Vazirani")

@login_required
@pages.route("/QuantumComputingLearning/BV_code_creation")
def BV_creation():
    ## randomly select an available processor
    session['processor'] = available_processors[int(np.random.random()*len(available_processors))]
    
    ## select an available processor with enough qubits
    for p in available_processors:
        if(p["number of qubits"] > 2):
            session['processor'] = p
            break
    n = session['processor']['number of qubits']
    if n < 2:
        flash("Our system has no available processor with enough qubits at the moment. Please try again later", "danger")
        return redirect(url_for(".QClearning"))
    
    ## generate secret code
    BV_code = []
    for i in range(n):
        r = np.random.random()
        if r<0.5:
            BV_code.append(0)
        else:
            BV_code.append(1)
    
    ## build Bernstein-Vazirani circuit
    qc = QuantumCircuit(n+1,n)
    qc.x(n)
    qc.h(range(n+1))
    
    # associate BV oracle
    qc = QuantumCircuit.compose(qc, BV_oracle(BV_code))
    
    # revert to computational basis for readout
    qc.h(range(n+1))
    qc.measure(range(n), range(n))

    ## submit job
    session["QASM"] = qc.qasm()
    session["instruction"] = session["QASM"].splitlines()
    transpile = QASM_Pulse_Transpiler(session["instruction"])
    transpile.extract_instructions()
    instructions_pulse = transpile.instruction.splitlines()
    
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    BV_string = ''
    for s in BV_code[::-1]:
        if(s == 0):
            BV_string += '0'
        else:
            BV_string += '1'
    job = Experiment(_id=uuid.uuid4().hex,
                    user_id=user._id,
                    processor=session["processor"],
                    category="BV",
                    params={"BV_code" : BV_string},
                    instructions=session["instruction"],
                    instructions_pulse=instructions_pulse,
                    date = datetime.datetime.today())
    current_app.db.open_jobs.insert_one(asdict(job))
    
    flash(f"Job has been submitted \n Your code was {BV_string}", "success")
    job_url = url_for(".openjob",_jobID=job._id, _external=True)
    html = render_template("notifications/notification_BV_job_submitted.html", BV_code = BV_string, job_url=job_url)
    subject = "SaxonQ: You submitted a job"
    if not session.get("is_admin"):
        email.send_message(user.email, subject, html)
    return redirect(url_for(".QClearning"))

@login_required
@pages.route("/QuantumComputingLearning/Simons_algorithm")
def Simon():
    return render_template("QClearning/Simon.html", title="SaxonQ -- Simon")

@login_required
@pages.route("/QuantumComputingLearning/Simons_algorithm_creation")
def Simon_creation():
    ## randomly select an available processor
    session['processor'] = available_processors[int(np.random.random()*len(available_processors))]
    
    ## select an available processor with enough qubits
    for p in available_processors:
        if(p["number of qubits"] > 2):
            session['processor'] = p
            break
    n = session['processor']['number of qubits']
    if n < 2:
        flash("Our system has no available processor with enough qubits at the moment. Please try again later", "danger")
        return redirect(url_for(".QClearning"))
    
    ## generate secret code
    Simon_code = ''
    for i in range(int(n/2)):
        r = np.random.random()
        if r<0.5:
            Simon_code += '0'
        else:
            Simon_code += '1'
    l = len(Simon_code)
    
    ## build Simon circuit
    qc = QuantumCircuit(n, l)
    
    # Quantum parallelism step
    qc.h(range(l))

    # Simon oracle
    qc = QuantumCircuit.compose(qc, Simon_oracle(Simon_code))
    
    qc.h(range(l))
    qc.measure(range(l),range(l))
    
    ## submit job
    session["QASM"] = qc.qasm()
    session["instruction"] = session["QASM"].splitlines()
    transpile = QASM_Pulse_Transpiler(session["instruction"])
    transpile.extract_instructions()
    instructions_pulse = transpile.instruction.splitlines()
    
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    Simon_string = ''
    for s in Simon_code[::-1]:
        if(s == '0'):
            Simon_string += '0'
        else:
            Simon_string += '1'
    job = Experiment(_id=uuid.uuid4().hex,
                    user_id=user._id,
                    processor=session["processor"],
                    category="Simon",
                    params={"Simon_code" : Simon_string},
                    instructions=session["instruction"],
                    instructions_pulse=instructions_pulse,
                    date = datetime.datetime.today())
    current_app.db.open_jobs.insert_one(asdict(job))
    
    flash(f"Job has been submitted \n Your code was {Simon_string}", "success")
    job_url = url_for(".openjob",_jobID=job._id, _external=True)
    html = render_template("notifications/notification_Simon_job_submitted.html", Simon_code = Simon_string, job_url=job_url)
    subject = "SaxonQ: You submitted a job"
    if not session.get("is_admin"):
        email.send_message(user.email, subject, html)
    return redirect(url_for(".QClearning"))


@login_required
@pages.route("/QuantumComputingLearning/Grover_algorithm")
def Grover():
    return render_template("QClearning/Grover.html", title="SaxonQ -- Grover")

@login_required
@pages.route("/QuantumComputingLearning/Grover_algorithm_creation")
def Grover_creation():
    ## randomly select an available processor
    session['processor'] = available_processors[int(np.random.random()*len(available_processors))]
    
    ## select an available processor with enough qubits
    for p in available_processors:
        if(p["number of qubits"] > 2):
            session['processor'] = p
            break
    n = session['processor']['number of qubits']

    if n < 2:
        flash("Our system has no available processor with enough qubits at the moment. Please try again later", "danger")
        return redirect(url_for(".QClearning"))
    
    omega = format(int(2**(n-1)*np.random.random()),'b').zfill(n-1)[::1]
    qc = QuantumCircuit(n,n-1)

    # set up the phase and uncomputaion circuits
    phase = GroverPhaseOracle(n, omega)
    inversion = GroverInversionOracle(n)

    ## prepare quantum parallelism state
    qc.h(range(n-1))
    
    # calculate number of times T Grover inversion has to be run
    T = np.pi*np.sqrt(2**(n-1))/4
    T_low = np.floor(T)
    T_high= np.ceil(T)
    if(abs(T-T_low) <= abs(T-T_high)):
        T = int(T_low)-1
    else:
        T = int(T_high)-1
    for _ in range(T):
        qc = QuantumCircuit.compose(qc, phase)
        qc = QuantumCircuit.compose(qc, inversion)
    qc.h(range(n-1))
    qc.measure(range(n-1), range(n-1))
    backend = Aer.get_backend('qasm_simulator')
    ex = execute(qc, backend, shots=1000)
    results = ex.result()
    count = results.get_counts()
    if(omega[::-1] == str(list(count.keys())[0])):
        pass
    else:
        qc.clear()
        qc.h(range(n-1))
        T = T+1
        for _ in range(T):
            qc = QuantumCircuit.compose(qc, phase)
            qc = QuantumCircuit.compose(qc, inversion)
        qc.h(range(n-1))
        qc.measure(range(n-1), range(n-1))
        backend = Aer.get_backend('qasm_simulator')
        ex = execute(qc, backend, shots=1000)
        results = ex.result()
        count = results.get_counts()
        if(omega[::-1] == str(list(count.keys())[0])):
            pass
        else:
            qc.clear()
            qc.h(range(n-1))
            T = T+1
            for _ in range(T):
                qc = QuantumCircuit.compose(qc, phase)
                qc = QuantumCircuit.compose(qc, inversion)
            qc.h(range(n-1))
            qc.measure(range(n-1), range(n-1))
            backend = Aer.get_backend('qasm_simulator')
            ex = execute(qc, backend, shots=1000)
            results = ex.result()
            count = results.get_counts()

    ## submit job
    session["QASM"] = qc.qasm()
    session["instruction"] = session["QASM"].splitlines()
    transpile = QASM_Pulse_Transpiler(session["instruction"])
    transpile.extract_instructions()
    instructions_pulse = transpile.instruction.splitlines()
    
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    Grover_string = ''
    for s in omega:
        Grover_string += s
    job = Experiment(_id=uuid.uuid4().hex,
                    user_id=user._id,
                    processor=session["processor"],
                    category="Grover",
                    params={"Grover_state" : Grover_string,
                            "Grover_iterations": T},
                    instructions=session["instruction"],
                    instructions_pulse=instructions_pulse,
                    date = datetime.datetime.today())
    current_app.db.open_jobs.insert_one(asdict(job))
    
    flash(f"Job has been submitted \n Your state was {Grover_string}", "success")
    job_url = url_for(".openjob",_jobID=job._id, _external=True)
    html = render_template("notifications/notification_Grover_job_submitted.html", Grover_state = Grover_string, job_url=job_url)
    subject = "SaxonQ: You submitted a job"
    if not session.get("is_admin"):
        email.send_message(user.email, subject, html)
    return redirect(url_for(".QClearning"))

@login_required
@pages.route("/QuantumComputingLearning/Shor_algorithm")
def Shor():
    return render_template("QClearning/Shor.html", title="SaxonQ -- Shor")

@login_required
@pages.route("/QuantumComputingLearning/Shor_algorithm_creation")
def Shor_creation():
    N = np.random.choice([15, 21, 35])
    if(N==15):
        a = np.random.choice([2, 7, 8, 11, 13])
    elif(N==21):
        a = 2
    elif(N==35):
        a = 4
    n_q = len("{0:b}".format(N)) + 1

    ## randomly select an available processor
    session['processor'] = available_processors[int(np.random.random()*len(available_processors))]
    
    ## select an available processor with enough qubits
    for p in available_processors:
        if(p["number of qubits"] >= n_q):
            session['processor'] = p
            break
    n = session['processor']['number of qubits']
    
    if n < n_q:
        flash("Our system has no available processor with enough qubits at the moment. Please try again later", "danger")
        return redirect(url_for(".QClearning"))
    qc = Shor_Kitaev(N=N,a=a)

    ## submit job
    session["QASM"] = qc.qasm()
    print(session["QASM"])
    session["instruction"] = session["QASM"].splitlines()
    #transpile = QASM_Pulse_Transpiler(session["instruction"])
    #transpile.extract_instructions()
    #instructions_pulse = transpile.instruction.splitlines()
    instructions_pulse = 'NOT YET WORKING'
    user_data = current_app.db.user.find_one({"email": session["email"]})
    user = User(**user_data)
    job = Experiment(_id=uuid.uuid4().hex,
                    user_id=user._id,
                    processor=session["processor"],
                    category="Shor",
                    params={"N" : str(N),
                            "a": str(a)},
                    instructions=session["instruction"],
                    instructions_pulse=instructions_pulse,
                    date = datetime.datetime.today())
    current_app.db.open_jobs.insert_one(asdict(job))
    
    flash(f"Job has been submitted \n Your number N was {N} and your random seed a was {a}", "success")
    job_url = url_for(".openjob",_jobID=job._id, _external=True)
    html = render_template("notifications/notification_Shor_job_submitted.html", N = N, a = a, job_url=job_url)
    subject = "SaxonQ: You submitted a job"
    if not session.get("is_admin"):
        email.send_message(user.email, subject, html)
    return redirect(url_for(".QClearning"))